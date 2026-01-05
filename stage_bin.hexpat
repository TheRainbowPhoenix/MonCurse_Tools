#include <std/sys.pat>
#include <std/mem.pat>
#include <std/string.pat>

// --- Helper Formatting Functions ---

fn format_simple(ref auto t) {
    if (t.val == 0) return "Empty";
    return std::format("ID: {:d} (Raw: 0x{:02X})", t.val - 1, t.val);
};

fn format_auto(ref auto t) {
    if (t.val == 0) return "Empty";
    return std::format("ID: {:d} | Auto: ({:d}, {:d})", t.val - 1, t.ax, t.ay);
};

fn format_flip(ref auto t) {
    if (t.val == 0) return "Empty";
    return std::format("ID: {:d} | Flip: {}", t.val - 1, t.flip ? "True" : "False");
};

// --- Tile Structures ---

struct TileSimple {
    u8 val   [[color("6070A0")]];
} [[format("format_simple")]];

struct TileAutotile {
    u8 val [[color("60A020")]];
    u8 ax  [[color("60A020")]];
    u8 ay  [[color("60A020")]];
} [[format("format_auto")]];

struct TileFlip {
    u8 val    [[color("A17020")]];
    bool flip  [[color("A17020")]];
} [[format("format_flip")]];

// --- Layer Structures (Dynamic Arrays) ---

struct LayerSimple {
    TileSimple tiles[parent.count];
};

struct LayerAutotile {
    TileAutotile tiles[parent.count];
};

struct LayerFlip {
    TileFlip tiles[parent.count];
};

// --- Footer Structures ---

struct Numberwang {
    u8 x;
    u8 y;
    u16 z;
};

struct Footer {
    u8 count;
    Numberwang items[count];
};

// --- Main Map Structure ---

struct LevelFile {
    u8 width;
    u8 height;
    
    // Calculated total tiles for array sizing
    u32 count = width * height;

    // 1. constructmap (Auto)
    LayerAutotile constructmap;
    
    // 2. constructmapedges (Auto)
    LayerAutotile constructmapedges;
    
    // 3. constructbackground (Auto)
    LayerAutotile constructbackground;
    
    // 4. backgroundfeatures (Flip)
    LayerFlip backgroundfeatures;
    
    // 5. Map (Auto)
    LayerAutotile Map;
    
    // 6. Mapedges (Auto)
    LayerAutotile Mapedges;
    
    // 7. Mapbackground (Auto)
    LayerAutotile Mapbackground;
    
    // 8. paths (Simple)
    LayerSimple paths;
    
    // 9. features (Flip)
    LayerFlip features;
    
    // 10. roofmap (Auto)
    LayerAutotile roofmap;
    
    // 11. foliage (Flip)
    LayerFlip foliage;
    
    // 12. shards (Simple)
    LayerSimple shards;
    
    // 13. watermap (Auto)
    LayerAutotile watermap;
    
    // 14. cummap (Flip)
    LayerFlip cummap;
    
    // 15. spawnmarker (Simple)
    LayerSimple spawnmarker;
    
    // 16. destructiblefeatures (Flip)
    LayerFlip destructiblefeatures;
    
    // 17. watermaptops (Simple)
    LayerSimple watermaptops;

    // Footer
    Footer footer;
};

// Define the file entry point
LevelFile level @ 0x00;
