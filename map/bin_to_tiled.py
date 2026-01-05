import struct
import os
import re
import sys
import xml.etree.ElementTree as ET
from xml.dom import minidom
import math

# --- CONFIGURATION ---
TILE_SIZE = 128
TSCN_PATH = "main.tscn"

# Map Layer Names to .tres files OR .tscn parsing
LAYER_CONFIG = {
    "constructbackground": "Tilemaps/constructbackground.tres",
    "constructbackground/backgroundfeatures": "Tilemaps/backgroundfeatures.tres",
    "constructmap": "Tilemaps/constructmap.tres",
    "constructmapedges": "Tilemaps/constructmapedges.tres",
    "Map": "Tilemaps/map.tres",
    "Mapedges": "Tilemaps/mapedges.tres",
    "paths": "Tilemaps/paths.tres",
    "features": "Tilemaps/features.tres",
    "roofmap": "Tilemaps/roofmap.tres",
    "foliage": "Tilemaps/foliage.tres",
    "shards": "Tilemaps/shards.tres",
    "watermap": "Tilemaps/water.tres",
    "watermaptops": "Tilemaps/water.tres",
    "cummap": "Tilemaps/cumtiles.tres",
    "destructiblefeatures": "Tilemaps/isometrictiles.tres",
    
    # SPECIAL HANDLING
    "Mapbackground": "USE_MAIN_TSCN", 
    "spawnmarker": "DIRECT_ICON_MAPPING" 
}

# Binary Reading Order (Matches Godot Script)
BINARY_READ_ORDER = [
    "constructmap", "constructmapedges", "constructbackground", 
    "constructbackground/backgroundfeatures", "Map", "Mapedges", 
    "Mapbackground", "paths", "features", "roofmap", "foliage", 
    "shards", "watermap", "cummap", "spawnmarker", 
    "destructiblefeatures", "watermaptops"
]

# Visual Order in Tiled (Bottom to Top)
VISUAL_ORDER = [
	"Mapbackground",                         # -40
	"constructbackground",                   # -35
	"limitrock",                             # -4
	"Mapedges",                              # -3
	"constructmapedges",                     # -2

	"CanvasLayer/ParallaxBackground/treesback/TileMap",   # 0
	"CanvasLayer/ParallaxBackground/treesfront/TileMap",  # 0
	"constructbackground/backgroundfeatures",             # 0

	"foliage",                               # 2

	"constructmap",                          # 3
	"paths",                                 # 3
	"features",                              # 3
	"destructiblefeatures",                  # 3
	"roofmap",                               # 3  (kept after the others because it appears later in the file)

	"shards",                                # 4
	"cummap",                                # 4

	"CanvasLayer3/fogofwar",                 # 5
	"watermap",                              # 10
	"Map",                                   # 12
	"watermaptops",                          # 13
	"limitfog",                              # 13 (after watermaptops due to file order)
	"Previewgrid",                           # 15
    "spawnmarker"
]



# Parsing Constants
TYPE_AUTOTILE = 1 
TYPE_FLIP = 2     
TYPE_SIMPLE = 3   

LAYER_TYPES = {
    "constructmap": TYPE_AUTOTILE, "constructmapedges": TYPE_AUTOTILE, 
    "constructbackground": TYPE_AUTOTILE, "Map": TYPE_AUTOTILE, 
    "Mapedges": TYPE_AUTOTILE, "Mapbackground": TYPE_AUTOTILE, 
    "roofmap": TYPE_AUTOTILE, "watermap": TYPE_AUTOTILE,
    "constructbackground/backgroundfeatures": TYPE_FLIP, "features": TYPE_FLIP, 
    "foliage": TYPE_FLIP, "cummap": TYPE_FLIP, "destructiblefeatures": TYPE_FLIP,
    "paths": TYPE_SIMPLE, "shards": TYPE_SIMPLE, 
    "spawnmarker": TYPE_SIMPLE, "watermaptops": TYPE_SIMPLE
}

FLIPPED_HORIZONTALLY_FLAG = 0x80000000

# --- CLASSES ---

class TileDefinition:
    def __init__(self, godot_id, texture_path, region, stride, tile_mode):
        self.godot_id = godot_id
        self.texture_path = texture_path # Relative path to PNG
        self.region = region # [x, y, w, h]
        self.stride = stride # [w, h]
        self.tile_mode = tile_mode # 0=Single, 1=Auto, 2=Atlas

class ImageTileset:
    def __init__(self, rel_path):
        self.rel_path = rel_path
        # Sanitize filename for Tiled
        clean_name = os.path.basename(rel_path).replace('.', '_')
        self.tsx_name = clean_name + ".tsx"
        self.width = 0
        self.height = 0
        self.firstgid = 0
        # Grid dimensions (Tiles)
        self.cols = 0
        self.rows = 0

# --- HELPERS ---

def clean_path(p):
    return os.path.normpath(p).replace('\\', '/')

def get_grid_dim(pixels):
    """ 
    Calculates columns/rows using Ceiling Division.
    Ensures 8px image counts as 1 Column, not 0.
    """
    if pixels <= 0: return 0
    return (pixels + TILE_SIZE - 1) // TILE_SIZE

def get_image_dimensions(path):
    if not os.path.exists(path): return None, None
    with open(path, 'rb') as f:
        data = f.read(30) # Read enough for header + IHDR
        
        if data[:8] != b'\x89PNG\r\n\x1a\n':
            return None, None # Not a PNG
        
        # Find IHDR chunk
        ihdr_start = data.find(b'IHDR')
        if ihdr_start == -1:
            return None, None
            
        # IHDR data starts 4 bytes after 'IHDR'
        # Width (4 bytes), Height (4 bytes)
        w_start = ihdr_start + 4
        h_start = w_start + 4
        
        w = struct.unpack('>I', data[w_start:w_start+4])[0]
        h = struct.unpack('>I', data[h_start:h_start+4])[0]
        return w, h

# --- PARSERS ---

def parse_definitions_string(content, ext_res_map):
    tile_defs = {}

    # 2. Extract Tile IDs
    ids = set(re.findall(r'^(\d+)/name', content, re.MULTILINE))

    for tid in ids:
        tid = int(tid)
        
        # Get Texture
        tex_match = re.search(f'^{tid}/texture = ExtResource\(\s*(\d+)\s*\)', content, re.MULTILINE)
        if not tex_match: continue
        
        res_id = int(tex_match.group(1))
        if res_id not in ext_res_map: continue
        
        tex_path = ext_res_map[res_id]

        # Get Region
        reg_match = re.search(f'^{tid}/region = Rect2\(\s*([-\d\.]+),\s*([-\d\.]+),\s*([-\d\.]+),\s*([-\d\.]+)\s*\)', content, re.MULTILINE)
        region = [float(x) for x in reg_match.groups()] if reg_match else [0,0,TILE_SIZE,TILE_SIZE]

        # Get Stride
        stride_match = re.search(f'^{tid}/autotile/tile_size = Vector2\(\s*([-\d\.]+),\s*([-\d\.]+)\s*\)', content, re.MULTILINE)
        stride = [float(x) for x in stride_match.groups()] if stride_match else [TILE_SIZE, TILE_SIZE]

        # Tile Mode (0=SINGLE, 1=AUTO, 2=ATLAS)
        mode_match = re.search(f'^{tid}/tile_mode = (\d+)', content, re.MULTILINE)
        mode = int(mode_match.group(1)) if mode_match else 0

        tile_defs[tid] = TileDefinition(tid, tex_path, region, stride, mode)

    return tile_defs

def parse_tres_for_tile_defs(tres_path):
    if not os.path.exists(tres_path): return {}
    with open(tres_path, 'r') as f: content = f.read()

    ext_res_map = {}
    matches = re.findall(r'\[ext_resource path="res://(.*?)" type="Texture" id=(\d+)\]', content)
    for path, id_str in matches:
        ext_res_map[int(id_str)] = clean_path(path)
    return parse_definitions_string(content, ext_res_map)

def parse_tscn_subresource(tscn_path, sub_id):
    """ Extracts a SubResource TileSet from main.tscn """
    if not os.path.exists(tscn_path): return {}
    with open(tscn_path, 'r') as f: content = f.read()

    # 1. Parse ExtResources (Global)
    ext_res_map = {}
    matches = re.findall(r'\[ext_resource path="res://(.*?)" type="Texture" id=(\d+)\]', content)
    for path, id_str in matches:
        ext_res_map[int(id_str)] = clean_path(path)

    # 2. Extract SubResource Block
    # [sub_resource type="TileSet" id=16] ... next [
    pattern = f'\[sub_resource type="TileSet" id={sub_id}\](.*?)(\[\w)'
    match = re.search(pattern, content, re.DOTALL)
    
    if not match:
        print(f"Error: SubResource id={sub_id} not found in {tscn_path}")
        return {}
    
    sub_content = match.group(1)
    return parse_definitions_string(sub_content, ext_res_map)

def create_tsx(image_ts):
    """ Generates a TSX file for a specific PNG image """
    if not os.path.exists(image_ts.rel_path):
        print(f"Warning: Image not found {image_ts.rel_path}")
        return

    w, h = get_image_dimensions(image_ts.rel_path)
    if w is None:
        print(f"ERROR: Image not found '{image_ts.rel_path}'. Using 128x128 placeholder.")
        w, h = 128, 128

    image_ts.width = w
    image_ts.height = h
    # Use Ceiling Logic so tiny images get at least 1 column
    image_ts.cols = get_grid_dim(w)
    image_ts.rows = get_grid_dim(h)

    root = ET.Element("tileset")
    root.set("version", "1.9")
    root.set("tiledversion", "1.9.2")
    root.set("name", os.path.basename(image_ts.rel_path))
    root.set("tilewidth", str(TILE_SIZE))
    root.set("tileheight", str(TILE_SIZE))
    root.set("spacing", "0")
    root.set("margin", "0")
    root.set("tilecount", str(image_ts.cols * image_ts.rows))
    root.set("columns", str(image_ts.cols))

    image = ET.SubElement(root, "image")
    image.set("source", image_ts.rel_path)
    image.set("width", str(w))
    image.set("height", str(h))

    xmlstr = minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")
    # Remove header
    xmlstr = "\n".join(xmlstr.split('\n')[1:]) 
    
    with open(image_ts.tsx_name, "w") as f:
        f.write(xmlstr)
    print(f"Generated {image_ts.tsx_name} [{image_ts.cols}x{image_ts.rows}]")

# --- MAIN LOGIC ---

def convert(bin_path):
    if not os.path.exists(bin_path):
        print("Binary file not found.")
        return

    # 1. SCAN TRES
    layer_tile_definitions = {}
    
    # Dict: TexturePath -> ImageTileset Object
    unique_images = {} 

    # 1a. Handle Mapbackground (TSCN SubResource)
    # The SubResource ID for Mapbackground is 16 in your main.tscn provided
    defs = parse_tscn_subresource(TSCN_PATH, 16)
    layer_tile_definitions["Mapbackground"] = defs
    for t_def in defs.values():
        if t_def.texture_path not in unique_images:
            unique_images[t_def.texture_path] = ImageTileset(t_def.texture_path)

    # 1b. Handle Spawnmarker (Virtual)
    spawn_icon_path = "Tilemaps/newsandstone.png"
    if spawn_icon_path not in unique_images:
        unique_images[spawn_icon_path] = ImageTileset(spawn_icon_path)

    # 1c. Handle Normal Layers
    for layer, tres_file in LAYER_CONFIG.items():
        if tres_file == "USE_MAIN_TSCN" or tres_file == "DIRECT_ICON_MAPPING": continue
        
        if layer not in layer_tile_definitions:
            defs = parse_tres_for_tile_defs(tres_file)
            layer_tile_definitions[layer] = defs
            
            # Register Images found
            for t_def in defs.values():
                if t_def.texture_path not in unique_images:
                    unique_images[t_def.texture_path] = ImageTileset(t_def.texture_path)

    # 2. GENERATE TSX FOR EVERY UNIQUE IMAGE
    print(f"Found {len(unique_images)} unique textures.")
    sorted_img_paths = sorted(unique_images.keys())
    
    current_firstgid = 1
    print("\n--- Generating Tilesets ---")
    for path in sorted_img_paths:
        img_ts = unique_images[path]
        img_ts.firstgid = current_firstgid
        create_tsx(img_ts)
        
        count = img_ts.cols * img_ts.rows
        print(f"GID {current_firstgid} -> {current_firstgid + count - 1} : {img_ts.tsx_name} ({img_ts.width}x{img_ts.height})")
        current_firstgid += count

    # 3. PARSE BINARY LEVEL
    print(f"Parsing {bin_path}...")
    with open(bin_path, 'rb') as f:
        bin_data = f.read()

    ptr = 0
    def get8():
        nonlocal ptr
        if ptr >= len(bin_data):
            print("OVERFLOW PTR !!")
            return 0
        val = bin_data[ptr]
        ptr += 1
        return val

    width = get8()
    height = get8()
    print(f"Level Size: {width}x{height}")

    parsed_layers = {} # LayerName -> CSV String

    for layer_name in BINARY_READ_ORDER:
        parse_type = LAYER_TYPES.get(layer_name, TYPE_SIMPLE)
        tile_defs = layer_tile_definitions.get(layer_name, {})
        
        layer_gids = []

        for x in range(width):
            col = []
            for y in range(height):
                val = get8()
                tile_id = val - 1 
                
                final_gid = 0

                # Data consumption logic
                auto_x = 0
                auto_y = 0
                flip = False

                if parse_type == TYPE_AUTOTILE:
                    auto_x = get8()
                    auto_y = get8()
                elif parse_type == TYPE_FLIP:
                    flip = (get8() == 1)

                if tile_id >= 0:
                    if layer_name == "spawnmarker":
                        img_ts = unique_images.get(spawn_icon_path)
                        if img_ts:
                            # Direct mapping: Val 1 -> Icon 0 (GID + 0)
                            # Godot Binary stores ID+1. We want index = ID.
                            local_id = tile_id 
                            if local_id < (img_ts.cols * img_ts.rows):
                                final_gid = img_ts.firstgid + local_id
                            else:
                                final_gid = img_ts.firstgid # Out of bounds fallback
                    
                    # STANDARD & MAPBACKGROUND
                    elif tile_id in tile_defs:
                        t_def = tile_defs[tile_id]
                        if t_def.texture_path in unique_images:
                            img_ts = unique_images[t_def.texture_path]
                            pixel_x = t_def.region[0]
                            pixel_y = t_def.region[1]
                            if t_def.tile_mode > 0:
                                pixel_x += (auto_x * t_def.stride[0])
                                pixel_y += (auto_y * t_def.stride[1])
                            
                            grid_x = int(round(pixel_x / TILE_SIZE))
                            grid_y = int(round(pixel_y / TILE_SIZE))
                            
                            if grid_x < img_ts.cols and grid_y < img_ts.rows:
                                local_id = grid_x + (grid_y * img_ts.cols)
                                final_gid = img_ts.firstgid + local_id
                                if flip: final_gid |= FLIPPED_HORIZONTALLY_FLAG

                col.append(final_gid)
            layer_gids.append(col)
        
        tiled_csv_lines = []
        for y in range(height):
            row = [str(layer_gids[x][y]) for x in range(width)]
            tiled_csv_lines.append(",".join(row))
        parsed_layers[layer_name] = ",\n".join(tiled_csv_lines)

    # 4. WRITE TMX
    root = ET.Element("map")
    root.set("version", "1.9")
    root.set("tiledversion", "1.9.2")
    root.set("orientation", "orthogonal")
    root.set("renderorder", "right-down")
    root.set("width", str(width))
    root.set("height", str(height))
    root.set("tilewidth", str(TILE_SIZE))
    root.set("tileheight", str(TILE_SIZE))
    root.set("infinite", "0")

    # Add Tilesets (Images)
    for path in sorted_img_paths:
        ts = unique_images[path]
        ts_node = ET.SubElement(root, "tileset")
        ts_node.set("firstgid", str(ts.firstgid))
        ts_node.set("source", ts.tsx_name)

    # Add Layers
    lid = 1
    for layer_name in VISUAL_ORDER:
        if layer_name not in parsed_layers: continue
        
        layer = ET.SubElement(root, "layer")
        layer.set("id", str(lid))
        layer.set("name", layer_name)
        layer.set("width", str(width))
        layer.set("height", str(height))
        
        data = ET.SubElement(layer, "data")
        data.set("encoding", "csv")
        data.text = "\n" + parsed_layers[layer_name] + "\n"
        lid += 1

    output_file = os.path.basename(bin_path).replace(".bin", ".tmx")
    xmlstr = minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")
    with open(output_file, "w") as f:
        f.write(xmlstr)

    print(f"Done! Saved {output_file}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        
        convert(r"fixedscenes\levelselect1.bin")
    else:
        convert(sys.argv[1])