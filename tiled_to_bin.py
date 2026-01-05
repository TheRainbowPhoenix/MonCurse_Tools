import struct
import os
import re
import sys
import xml.etree.ElementTree as ET

# --- CONFIGURATION ---
TILE_SIZE = 128
TSCN_PATH = "main.tscn"

LAYER_TO_TRES = {
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
    "Mapbackground": "USE_MAIN_TSCN",
    "spawnmarker": "DIRECT_ICON_MAPPING"
}

BINARY_WRITE_ORDER = [
    "constructmap", "constructmapedges", "constructbackground", 
    "constructbackground/backgroundfeatures", "Map", "Mapedges", 
    "Mapbackground", "paths", "features", "roofmap", "foliage", 
    "shards", "watermap", "cummap", "spawnmarker", 
    "destructiblefeatures", "watermaptops"
]

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
GID_MASK                  = 0x1FFFFFFF

class TileDefinition:
    def __init__(self, godot_id, texture_path, region, stride):
        self.godot_id = godot_id
        self.texture_path = texture_path 
        self.region = region 
        self.stride = stride 

class TilesetInfo:
    def __init__(self, firstgid, source_tsx):
        self.firstgid = firstgid
        self.source_tsx = source_tsx
        self.image_path = None
        self.columns = 0

def parse_tile_definitions_from_string(content, ext_res_map):
    defs = []
    ids = set(re.findall(r'^(\d+)/name', content, re.MULTILINE))
    for tid in ids:
        tid = int(tid)
        tex_match = re.search(f'^{tid}/texture = ExtResource\(\s*(\d+)\s*\)', content, re.MULTILINE)
        if not tex_match: continue
        res_id = int(tex_match.group(1))
        if res_id not in ext_res_map: continue
        tex_path = ext_res_map[res_id]
        reg_match = re.search(f'^{tid}/region = Rect2\(\s*([-\d\.]+),\s*([-\d\.]+),\s*([-\d\.]+),\s*([-\d\.]+)\s*\)', content, re.MULTILINE)
        region = [float(x) for x in reg_match.groups()] if reg_match else [0.0, 0.0, float(TILE_SIZE), float(TILE_SIZE)]
        stride_match = re.search(f'^{tid}/autotile/tile_size = Vector2\(\s*([-\d\.]+),\s*([-\d\.]+)\s*\)', content, re.MULTILINE)
        stride = [float(x) for x in stride_match.groups()] if stride_match else [float(TILE_SIZE), float(TILE_SIZE)]
        defs.append(TileDefinition(tid, tex_path, region, stride))
    return defs

def parse_tres_definitions(tres_path):
    if not os.path.exists(tres_path): return []
    with open(tres_path, 'r') as f: content = f.read()
    ext_res_map = {}
    matches = re.findall(r'\[ext_resource path="res://(.*?)" type="Texture" id=(\d+)\]', content)
    for path, id_str in matches:
        ext_res_map[int(id_str)] = os.path.normpath(path).replace('\\', '/')
    return parse_tile_definitions_from_string(content, ext_res_map)

def parse_tscn_subresource(tscn_path, sub_id):
    if not os.path.exists(tscn_path): return []
    with open(tscn_path, 'r') as f: content = f.read()
    ext_res_map = {}
    matches = re.findall(r'\[ext_resource path="res://(.*?)" type="Texture" id=(\d+)\]', content)
    for path, id_str in matches:
        ext_res_map[int(id_str)] = os.path.normpath(path).replace('\\', '/')
    pattern = f'\[sub_resource type="TileSet" id={sub_id}\](.*?)(\[\w)'
    match = re.search(pattern, content, re.DOTALL)
    if not match: return []
    return parse_tile_definitions_from_string(match.group(1), ext_res_map)

def get_godot_tile_from_pixel(layer_defs, texture_path, pixel_x, pixel_y):
    if texture_path:
        texture_path = texture_path.replace('\\', '/')
    for definition in layer_defs:
        if texture_path:
            if definition.texture_path not in texture_path and texture_path not in definition.texture_path:
                continue
        rx, ry, rw, rh = definition.region
        if (pixel_x >= rx - 0.1 and pixel_x < rx + rw - 0.1 and
            pixel_y >= ry - 0.1 and pixel_y < ry + rh - 0.1):
            offset_x = pixel_x - rx
            offset_y = pixel_y - ry
            auto_x = int(round(offset_x / definition.stride[0]))
            auto_y = int(round(offset_y / definition.stride[1]))
            return definition.godot_id, auto_x, auto_y
    return None, 0, 0

def parse_tsx(tsx_path):
    if not os.path.exists(tsx_path): return None, 0
    tree = ET.parse(tsx_path)
    root = tree.getroot()
    image_node = root.find("image")
    if image_node is None: return None, 0
    source = image_node.get("source")
    width = int(image_node.get("width"))
    clean_source = os.path.normpath(source).replace('\\', '/')
    columns = int(root.get("columns"))
    if columns == 0: columns = (width + TILE_SIZE - 1) // TILE_SIZE
    return clean_source, columns

def convert_tmx_to_bin(tmx_path):
    if not os.path.exists(tmx_path): return
    print("Parsing TMX...")
    tree = ET.parse(tmx_path)
    root = tree.getroot()
    
    map_width = int(root.get("width"))
    map_height = int(root.get("height"))
    
    tilesets = []
    for ts_node in root.findall("tileset"):
        firstgid = int(ts_node.get("firstgid"))
        source = ts_node.get("source")
        ts_info = TilesetInfo(firstgid, source)
        img_path, cols = parse_tsx(source)
        ts_info.image_path = img_path
        ts_info.columns = cols
        tilesets.append(ts_info)
    tilesets.sort(key=lambda x: x.firstgid, reverse=True)

    tmx_layers = {} 
    for layer in root.findall("layer"):
        name = layer.get("name")
        data_node = layer.find("data")
        text = data_node.text.strip()
        gids = [int(x) for x in text.replace('\n', '').split(',')]
        grid = [[0 for _ in range(map_height)] for _ in range(map_width)]
        for i, raw_gid in enumerate(gids):
            x = i % map_width
            y = i // map_width
            if x < map_width and y < map_height: grid[x][y] = raw_gid
        tmx_layers[name] = grid

    layer_definitions = {}
    
    # 1. TSCN SubResource
    layer_definitions["Mapbackground"] = parse_tscn_subresource(TSCN_PATH, 16)
    
    # 2. TRES Files
    for layer_name, tres_path in LAYER_TO_TRES.items():
        if layer_name not in layer_definitions and tres_path != "USE_MAIN_TSCN" and tres_path != "DIRECT_ICON_MAPPING":
            layer_definitions[layer_name] = parse_tres_definitions(tres_path)

    output_bin = tmx_path.replace(".tmx", ".bin")
    print(f"Writing {output_bin}...")
    
    with open(output_bin, "wb") as f:
        f.write(struct.pack('B', map_width))
        f.write(struct.pack('B', map_height))
        
        for layer_name in BINARY_WRITE_ORDER:
            layer_type = LAYER_TYPES.get(layer_name, TYPE_SIMPLE)
            grid = tmx_layers.get(layer_name)
            defs = layer_definitions.get(layer_name, [])

            for x in range(map_width):
                for y in range(map_height):
                    raw_gid = grid[x][y] if grid else 0
                    flipped_h = bool(raw_gid & FLIPPED_HORIZONTALLY_FLAG)
                    gid = raw_gid & GID_MASK
                    
                    final_id = 0
                    auto_x = 0
                    auto_y = 0
                    
                    if gid > 0:
                        target_ts = None
                        for ts in tilesets:
                            if gid >= ts.firstgid:
                                target_ts = ts
                                break
                        
                        if target_ts:
                            local_id = gid - target_ts.firstgid
                            
                            # --- OVERRIDE LOGIC ---
                            if layer_name == "spawnmarker":
                                # Direct linear mapping for icons
                                final_id = local_id + 1
                            else:
                                # Calculate texture pixel coords from Tiled GID
                                img_grid_x = local_id % target_ts.columns if target_ts.columns > 0 else 0
                                img_grid_y = local_id // target_ts.columns if target_ts.columns > 0 else 0
                                pixel_x = img_grid_x * TILE_SIZE
                                pixel_y = img_grid_y * TILE_SIZE
                                
                                # Reverse Lookup in Godot Defs
                                godot_id, ax, ay = get_godot_tile_from_pixel(defs, target_ts.image_path, pixel_x, pixel_y)
                                
                                if godot_id is not None:
                                    final_id = godot_id + 1 
                                    auto_x = ax
                                    auto_y = ay
                                else:
                                    # Fallback for Mapbackground if lookup fails (e.g. autotile grid)
                                    # We just trust the grid pos = auto pos
                                    if layer_name == "Mapbackground":
                                         # Assume Tile ID 1 (TestTiles) or 2 (Sandstone) based on image?
                                         # Simplified: Just grab the first def if available
                                         if defs:
                                             final_id = defs[0].godot_id + 1
                                             auto_x = img_grid_x
                                             auto_y = img_grid_y

                    f.write(struct.pack('B', final_id))
                    if layer_type == TYPE_AUTOTILE:
                        f.write(struct.pack('B', auto_x))
                        f.write(struct.pack('B', auto_y))
                    elif layer_type == TYPE_FLIP:
                        f.write(struct.pack('B', 1 if flipped_h else 0))
        
        f.write(struct.pack('B', 0))

    print("Conversion Complete.")

if __name__ == "__main__":
    if len(sys.argv) < 2: print("Usage: python tiled_to_bin_v8.py <map.tmx>")
    else: convert_tmx_to_bin(sys.argv[1])