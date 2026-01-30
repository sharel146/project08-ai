"""
PROJECT 08 - Unified Platform
Combines Shopify Store Assistant + 3D Model Generator with 3D Preview
"""

import streamlit as st
import streamlit.components.v1 as components
from google import genai
from google.genai import types
import requests
import subprocess
import re
import os
from anthropic import Anthropic
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum

# ============================================================================
# 3D PREVIEW GENERATOR (Built-in)
# ============================================================================

def parse_openscad_to_threejs(scad_code: str) -> List[Dict[str, Any]]:
    """Parse OpenSCAD code and extract primitives WITH their transformations"""
    objects = []
    
    # Remove comments
    code = re.sub(r'//.*', '', scad_code)
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
    
    # Find translated cubes
    translated_cube_pattern = r'translate\s*\(\s*\[([^\]]+)\]\s*\)\s*cube\s*\(\s*\[([^\]]+)\]'
    for match in re.finditer(translated_cube_pattern, code):
        try:
            pos = [float(x.strip()) for x in match.group(1).split(',')]
            size = [float(x.strip()) for x in match.group(2).split(',')]
            objects.append({
                'type': 'cube',
                'size': size,
                'position': pos
            })
        except:
            pass
    
    # Find non-translated cubes
    standalone_cube_pattern = r'(?<!translate\s{0,50})cube\s*\(\s*\[([^\]]+)\]'
    for match in re.finditer(standalone_cube_pattern, code):
        try:
            # Check if already captured as translated
            if not any(obj['type'] == 'cube' for obj in objects):
                size = [float(x.strip()) for x in match.group(1).split(',')]
                objects.append({
                    'type': 'cube',
                    'size': size,
                    'position': [0, 0, 0]
                })
        except:
            pass
    
    # Find translated cones/cylinders with r1/r2
    translated_cone_pattern = r'translate\s*\(\s*\[([^\]]+)\]\s*\)\s*cylinder\s*\([^)]*h\s*=\s*([\d.]+)[^)]*r1\s*=\s*([\d.]+)[^)]*r2\s*=\s*([\d.]+)'
    for match in re.finditer(translated_cone_pattern, code):
        try:
            pos = [float(x.strip()) for x in match.group(1).split(',')]
            h = float(match.group(2))
            r1 = float(match.group(3))
            r2 = float(match.group(4))
            objects.append({
                'type': 'cone',
                'height': h,
                'radiusTop': r1,
                'radiusBottom': r2,
                'position': pos
            })
        except:
            pass
    
    # Find non-translated cones with r1/r2
    standalone_cone_pattern = r'(?<!translate\s{0,50})cylinder\s*\([^)]*h\s*=\s*([\d.]+)[^)]*r1\s*=\s*([\d.]+)[^)]*r2\s*=\s*([\d.]+)'
    for match in re.finditer(standalone_cone_pattern, code):
        try:
            h = float(match.group(1))
            r1 = float(match.group(2))
            r2 = float(match.group(3))
            objects.append({
                'type': 'cone',
                'height': h,
                'radiusTop': r1,
                'radiusBottom': r2,
                'position': [0, 0, 0]
            })
        except:
            pass
    
    # Find translated regular cylinders
    translated_cylinder_pattern = r'translate\s*\(\s*\[([^\]]+)\]\s*\)\s*cylinder\s*\([^)]*h\s*=\s*([\d.]+)[^)]*(?:r\s*=\s*([\d.]+)|r1\s*=\s*([\d.]+))'
    for match in re.finditer(translated_cylinder_pattern, code):
        try:
            pos = [float(x.strip()) for x in match.group(1).split(',')]
            h = float(match.group(2))
            r = float(match.group(3) or match.group(4))
            objects.append({
                'type': 'cylinder',
                'height': h,
                'radius': r,
                'position': pos
            })
        except:
            pass
    
    # Find non-translated regular cylinders
    standalone_cylinder_pattern = r'(?<!translate\s{0,50})cylinder\s*\(\s*h\s*=\s*([\d.]+).*?r\s*=\s*([\d.]+)'
    for match in re.finditer(standalone_cylinder_pattern, code):
        try:
            h = float(match.group(1))
            r = float(match.group(2))
            # Only add if not already matched
            if not any(obj['type'] in ['cylinder', 'cone'] for obj in objects):
                objects.append({
                    'type': 'cylinder',
                    'height': h,
                    'radius': r,
                    'position': [0, 0, 0]
                })
        except:
            pass
    
    # Find spheres
    sphere_pattern = r'sphere\s*\(\s*r\s*=\s*([\d.]+)'
    for match in re.finditer(sphere_pattern, code):
        try:
            r = float(match.group(1))
            objects.append({
                'type': 'sphere',
                'radius': r,
                'position': [0, 0, 0]
            })
        except:
            pass
    
    # Default fallback if no objects found
    return objects if objects else [{'type': 'cube', 'size': [50, 50, 50], 'position': [0, 0, 0]}]


def generate_threejs_html(scad_code: str, height: int = 500) -> str:
    """Generate HTML with Three.js viewer for OpenSCAD code"""
    
    objects = parse_openscad_to_threejs(scad_code)
    
    return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ margin: 0; overflow: hidden; background: linear-gradient(135deg, #1a1a2e, #16213e); }}
        #viewer {{ width: 100%; height: {height}px; }}
        .controls {{
            position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%);
            background: rgba(0,0,0,0.7); padding: 10px 20px; border-radius: 20px;
            color: white; font-size: 12px; backdrop-filter: blur(10px);
        }}
        .info {{
            position: absolute; top: 20px; right: 20px;
            background: rgba(0,210,255,0.2); padding: 10px 15px; border-radius: 8px;
            color: #00d2ff; font-size: 14px; border: 1px solid rgba(0,210,255,0.3);
        }}
    </style>
</head>
<body>
    <div id="viewer"></div>
    <div class="info">🔷 3D Preview</div>
    <div class="controls">🖱️ Drag to rotate • Scroll to zoom</div>
    
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script>
        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0x16213e);
        
        const camera = new THREE.PerspectiveCamera(75, window.innerWidth / {height}, 0.1, 10000);
        const renderer = new THREE.WebGLRenderer({{ antialias: true }});
        renderer.setSize(window.innerWidth, {height});
        document.getElementById('viewer').appendChild(renderer.domElement);
        
        // Lighting
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
        scene.add(ambientLight);
        const directionalLight1 = new THREE.DirectionalLight(0xffffff, 0.8);
        directionalLight1.position.set(5, 10, 7);
        scene.add(directionalLight1);
        const directionalLight2 = new THREE.DirectionalLight(0x00d2ff, 0.3);
        directionalLight2.position.set(-5, -10, -7);
        scene.add(directionalLight2);
        
        // Materials
        const material = new THREE.MeshPhongMaterial({{
            color: 0x00d2ff, specular: 0x111111, shininess: 30
        }});
        const edgeMaterial = new THREE.LineBasicMaterial({{ color: 0x0088cc }});
        
        // Create model group
        const modelGroup = new THREE.Group();
        const objects = {objects};
        
        objects.forEach(obj => {{
            let mesh;
            
            if (obj.type === 'cube') {{
                const geometry = new THREE.BoxGeometry(obj.size[0], obj.size[2], obj.size[1]);
                mesh = new THREE.Mesh(geometry, material);
                const edges = new THREE.EdgesGeometry(geometry);
                mesh.add(new THREE.LineSegments(edges, edgeMaterial));
                // Use actual position + half dimensions for centering
                mesh.position.set(
                    obj.position[0] + obj.size[0]/2, 
                    obj.position[2] + obj.size[2]/2, 
                    obj.position[1] + obj.size[1]/2
                );
                
            }} else if (obj.type === 'cone') {{
                const geometry = new THREE.CylinderGeometry(
                    obj.radiusTop, 
                    obj.radiusBottom, 
                    obj.height, 
                    32
                );
                mesh = new THREE.Mesh(geometry, material);
                const edges = new THREE.EdgesGeometry(geometry);
                mesh.add(new THREE.LineSegments(edges, edgeMaterial));
                // Use actual position + half height
                mesh.position.set(
                    obj.position[0], 
                    obj.position[2] + obj.height/2, 
                    obj.position[1]
                );
                
            }} else if (obj.type === 'cylinder') {{
                const geometry = new THREE.CylinderGeometry(obj.radius, obj.radius, obj.height, 32);
                mesh = new THREE.Mesh(geometry, material);
                const edges = new THREE.EdgesGeometry(geometry);
                mesh.add(new THREE.LineSegments(edges, edgeMaterial));
                // Use actual position + half height
                mesh.position.set(
                    obj.position[0], 
                    obj.position[2] + obj.height/2, 
                    obj.position[1]
                );
                
            }} else if (obj.type === 'sphere') {{
                const geometry = new THREE.SphereGeometry(obj.radius, 32, 32);
                mesh = new THREE.Mesh(geometry, material);
                const edges = new THREE.EdgesGeometry(geometry);
                mesh.add(new THREE.LineSegments(edges, edgeMaterial));
                // Use actual position
                mesh.position.set(obj.position[0], obj.position[2], obj.position[1]);
            }}
            
            if (mesh) modelGroup.add(mesh);
        }});
        
        scene.add(modelGroup);
        
        // Auto-center camera
        const box = new THREE.Box3().setFromObject(modelGroup);
        const center = box.getCenter(new THREE.Vector3());
        const size = box.getSize(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z);
        const fov = camera.fov * (Math.PI / 180);
        let cameraZ = Math.abs(maxDim / 2 / Math.tan(fov / 2)) * 2.5;
        camera.position.set(cameraZ, cameraZ * 0.7, cameraZ);
        camera.lookAt(center);
        
        // Mouse controls
        let isDragging = false;
        let previousMousePosition = {{ x: 0, y: 0 }};
        
        renderer.domElement.addEventListener('mousedown', (e) => {{
            isDragging = true;
            previousMousePosition = {{ x: e.clientX, y: e.clientY }};
        }});
        
        renderer.domElement.addEventListener('mousemove', (e) => {{
            if (isDragging) {{
                modelGroup.rotation.y += (e.clientX - previousMousePosition.x) * 0.01;
                modelGroup.rotation.x += (e.clientY - previousMousePosition.y) * 0.01;
                previousMousePosition = {{ x: e.clientX, y: e.clientY }};
            }}
        }});
        
        renderer.domElement.addEventListener('mouseup', () => {{ isDragging = false; }});
        
        // Zoom with wheel
        renderer.domElement.addEventListener('wheel', (e) => {{
            e.preventDefault();
            camera.position.multiplyScalar(e.deltaY > 0 ? 1.1 : 0.9);
        }});
        
        // Auto-rotation
        let autoRotate = true;
        renderer.domElement.addEventListener('mouseenter', () => {{ autoRotate = false; }});
        renderer.domElement.addEventListener('mouseleave', () => {{ autoRotate = true; }});
        
        // Animation loop
        function animate() {{
            requestAnimationFrame(animate);
            if (autoRotate) modelGroup.rotation.y += 0.005;
            renderer.render(scene, camera);
        }}
        animate();
        
        // Resize handler
        window.addEventListener('resize', () => {{
            camera.aspect = window.innerWidth / {height};
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, {height});
        }});
    </script>
</body>
</html>
"""


# ============================================================================
# PAGE CONFIGURATION
# ============================================================================

st.set_page_config(
    page_title="Project 08 - Unified Platform",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    @keyframes gradientBG { 
        0% { background-position: 0% 50%; } 
        50% { background-position: 100% 50%; } 
        100% { background-position: 0% 50%; } 
    }
    
    html, body, [class*="css"] { 
        font-family: -apple-system, BlinkMacSystemFont, sans-serif; 
        background-color: #000; 
        color: #fff; 
    }
    
    .stApp { 
        background: linear-gradient(135deg, #0f0c29, #302b63, #24243e); 
        background-size: 400% 400%; 
        animation: gradientBG 15s ease infinite; 
    }
    
    /* Product Cards */
    .product-card { 
        background: rgba(255,255,255,0.05); 
        border: 1px solid rgba(255,255,255,0.1); 
        border-radius: 16px; 
        padding: 15px; 
        margin-bottom: 12px; 
        cursor: pointer; 
        backdrop-filter: blur(10px); 
        transition: all 0.3s ease; 
    }
    .product-card:hover { 
        transform: translateY(-5px); 
        border-color: #00d2ff; 
        background: rgba(255,255,255,0.15); 
        box-shadow: 0 5px 15px rgba(0,210,255,0.3); 
    }
    .product-img {
        width: 100%;
        border-radius: 10px;
        margin-bottom: 10px;
        object-fit: cover;
    }
    .card-title { font-weight: 600; font-size: 15px; color: #fff; margin-bottom: 4px; }
    .card-price { color: #00d2ff; font-size: 14px; font-weight: bold; }
    .card-qty { float: right; color: #aaa; font-size: 12px; }
    
    /* Chat Styling */
    div[data-testid="stChatMessage"] { background: transparent; border: none; padding: 0; }
    div[data-testid="stChatMessage"]:nth-child(odd) div[data-testid="stMarkdownContainer"] { 
        background: rgba(255,255,255,0.05); 
        border-radius: 20px 20px 20px 5px; 
        padding: 12px 18px; 
        color: #eee; 
        border: 1px solid rgba(255,255,255,0.05); 
    }
    div[data-testid="stChatMessage"]:nth-child(even) div[data-testid="stMarkdownContainer"] { 
        background: linear-gradient(135deg, #00d2ff, #3a7bd5); 
        border-radius: 20px 20px 5px 20px; 
        padding: 12px 18px; 
        color: #fff; 
        text-align: right; 
        box-shadow: 0 4px 15px rgba(0,210,255,0.2); 
    }
    
    .stMarkdown img { 
        border-radius: 12px; 
        margin-top: 10px; 
        max-width: 250px; 
        border: 1px solid rgba(255,255,255,0.1); 
    }
    
    .stTextInput input { 
        background: rgba(0,0,0,0.3) !important; 
        border: 1px solid rgba(255,255,255,0.2) !important; 
        color: white !important; 
        border-radius: 25px; 
        padding: 10px 15px; 
    }
    
    /* Success/Error Boxes */
    .success-box {
        background: rgba(0, 255, 127, 0.1);
        border: 2px solid rgba(0, 255, 127, 0.3);
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0;
    }
    
    .error-box {
        background: rgba(255, 69, 58, 0.1);
        border: 2px solid rgba(255, 69, 58, 0.3);
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0;
    }
    
    .mode-selector {
        background: rgba(255,255,255,0.1);
        border-radius: 10px;
        padding: 10px;
        margin-bottom: 20px;
    }
    
    #MainMenu, footer, header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ============================================================================
# API KEYS AND CONFIGURATION
# ============================================================================

def load_secrets():
    """Load API keys from Streamlit secrets"""
    secrets = {}
    
    # Shopify Store Keys
    try:
        secrets['google_api_key'] = st.secrets.get("GOOGLE_API_KEY", "")
        secrets['shopify_api_key'] = st.secrets.get("SHOPIFY_API_KEY", "")
        secrets['shopify_store_url'] = st.secrets.get("SHOPIFY_STORE_URL", "")
    except:
        secrets['google_api_key'] = ""
        secrets['shopify_api_key'] = ""
        secrets['shopify_store_url'] = ""
    
    # 3D Modeling Keys
    try:
        secrets['anthropic_api_key'] = st.secrets.get("ANTHROPIC_API_KEY", "")
    except:
        secrets['anthropic_api_key'] = ""
    
    return secrets

# ============================================================================
# SHOPIFY STORE FUNCTIONS
# ============================================================================

@st.cache_resource
def get_inventory(shopify_api_key, shopify_store_url):
    """Fetch products from Shopify"""
    if not shopify_api_key or not shopify_store_url:
        return []
    
    try:
        url = f"https://{shopify_store_url}/admin/api/2024-01/products.json?status=active&limit=50"
        headers = {"X-Shopify-Access-Token": shopify_api_key, "Content-Type": "application/json"}
        response = requests.get(url, headers=headers, timeout=3)
        if response.status_code == 200:
            products = response.json().get('products', [])
            raw_data = []
            for p in products:
                try:
                    title = p['title']
                    handle = p['handle']
                    variant = p['variants'][0]
                    price = variant['price']
                    qty = variant['inventory_quantity']
                    img = p['images'][0]['src'] if p.get('images') else ""
                    link = f"https://{shopify_store_url}/products/{handle}"
                    raw_data.append({"title": title, "price": price, "qty": qty, "link": link, "img": img})
                except: 
                    continue
            return raw_data
        return []
    except:
        return []

def get_store_system_instruction(inventory):
    """System instruction for store chatbot"""
    inv_text = "\n".join([f"- {p['title']} (Price: ${p['price']}, Link: {p['link']}, Image: {p['img']})" for p in inventory])
    return f"""
    You are the AI assistant for 'Project 08'.
    PROTOCOL:
    1. Language: English default. Hebrew ONLY if user writes in Hebrew.
    2. Currency: All prices are in USD ($).
    3. Style: Short, cool, sales-oriented.
    4. Images: You MUST display images like this: [![Product](ImageURL)](ProductLink)
    5. INVENTORY DATA:
    {inv_text}
    """

# ============================================================================
# 3D MODELING AGENT CLASSES
# ============================================================================

class Config:
    MODEL = "claude-sonnet-4-20250514"
    MAX_CORRECTION_ATTEMPTS = 5
    OPENSCAD_TIMEOUT = 30
    OPENSCAD_BINARY = "openscad"
    BUILD_VOLUME = {"x": 256, "y": 256, "z": 256}

class RequestType(Enum):
    FUNCTIONAL = "functional"
    ORGANIC = "organic"
    UNKNOWN = "unknown"

class ErrorCategory(Enum):
    SYNTAX = "syntax"
    UNDEFINED_VARIABLE = "undefined"
    INVALID_OPERATION = "invalid_op"
    GEOMETRY_ERROR = "geometry"
    COMPILATION_FAILED = "compilation"
    UNKNOWN = "unknown"

def categorize_error(error_message: str) -> Tuple[ErrorCategory, str]:
    error_lower = error_message.lower()
    if any(keyword in error_lower for keyword in ["syntax error", "parse error", "expected ';'"]):
        return ErrorCategory.SYNTAX, error_message
    if "not defined" in error_lower or "unknown variable" in error_lower:
        match = re.search(r"'([^']+)' .*not defined", error_message)
        var_name = match.group(1) if match else "unknown"
        return ErrorCategory.UNDEFINED_VARIABLE, f"Variable '{var_name}' not defined"
    if "division by zero" in error_lower or "invalid value" in error_lower:
        return ErrorCategory.INVALID_OPERATION, error_message
    if any(keyword in error_lower for keyword in ["geometry", "manifold", "invalid shape"]):
        return ErrorCategory.GEOMETRY_ERROR, error_message
    if "compilation failed" in error_lower:
        return ErrorCategory.COMPILATION_FAILED, error_message
    return ErrorCategory.UNKNOWN, error_message

class FallbackPatterns:
    @staticmethod
    def funnel(top_diameter: float = 100, bottom_diameter: float = 20, 
               height: float = 80, wall_thickness: float = 2) -> str:
        return f"""// Parametric Funnel WITH HOLE
top_d = {top_diameter};
bottom_d = {bottom_diameter};
height = {height};
wall = {wall_thickness};

difference() {{
    // Outer cone
    cylinder(h=height, r1=top_d/2, r2=bottom_d/2, $fn=100);
    
    // Inner cone (hollow)
    translate([0, 0, wall])
        cylinder(h=height, r1=(top_d/2)-wall, r2=(bottom_d/2)-wall, $fn=100);
    
    // Bottom opening (ensures liquid can flow through!)
    translate([0, 0, -1])
        cylinder(h=wall+2, r=(bottom_d/2)-wall, $fn=50);
}}

// Spout extension (hollow tube)
difference() {{
    translate([0, 0, -10])
        cylinder(h=10, r=bottom_d/2, $fn=50);
    translate([0, 0, -11])
        cylinder(h=12, r=(bottom_d/2)-wall, $fn=50);
}}
"""
    
    @staticmethod
    def bracket(width: float = 50, height: float = 40, 
                thickness: float = 5, hole_diameter: float = 5) -> str:
        return f"""// L-Bracket
width = {width};
height = {height};
thick = {thickness};
hole_d = {hole_diameter};

difference() {{
    union() {{
        cube([thick, width, height]);
        cube([width, width, thick]);
    }}
    translate([thick/2, width/2, height - 10])
        rotate([0, 90, 0])
        cylinder(h=thick*2, r=hole_d/2, center=true, $fn=30);
    translate([width - 10, width/2, thick/2])
        cylinder(h=thick*2, r=hole_d/2, center=true, $fn=30);
}}
"""
    
    @staticmethod
    def box(length: float = 100, width: float = 80, height: float = 60,
            wall_thickness: float = 2, lid: bool = False) -> str:
        lid_code = ""
        if lid:
            lid_code = f"""
translate([0, {width + 10}, 0])
difference() {{
    cube([{length}, {width}, 5]);
    translate([{wall_thickness}, {wall_thickness}, -1])
        cube([{length - 2*wall_thickness}, {width - 2*wall_thickness}, 7]);
}}
"""
        return f"""// Parametric Box
length = {length};
width = {width};
height = {height};
wall = {wall_thickness};

difference() {{
    cube([length, width, height]);
    translate([wall, wall, wall])
        cube([length - 2*wall, width - 2*wall, height]);
}}
{lid_code}
"""

class RequestClassifier:
    def __init__(self, client: Anthropic):
        self.client = client
    
    def classify(self, user_request: str) -> RequestType:
        prompt = f"""Classify: "{user_request}"
FUNCTIONAL (geometric/mechanical) or ORGANIC (sculptural/artistic)?
Respond with ONLY one word: FUNCTIONAL or ORGANIC"""
        
        try:
            response = self.client.messages.create(
                model=Config.MODEL,
                max_tokens=10,
                messages=[{"role": "user", "content": prompt}]
            )
            classification = response.content[0].text.strip().upper()
            if "FUNCTIONAL" in classification:
                return RequestType.FUNCTIONAL
            elif "ORGANIC" in classification:
                return RequestType.ORGANIC
            return RequestType.UNKNOWN
        except:
            return RequestType.UNKNOWN

class ModelGenerator:
    def __init__(self, client: Anthropic):
        self.client = client
    
    def generate(self, user_request: str) -> Tuple[bool, str, str]:
        """Generate OpenSCAD code from natural language"""
        system_prompt = f"""Expert OpenSCAD programmer for Bambu Lab A1.
BUILD: {Config.BUILD_VOLUME['x']}mm cube
RULES: Valid code only, $fn>=50, wall>=1.2mm, no explanations.
RESPOND WITH CODE ONLY."""
        
        try:
            with st.spinner("🤖 Generating code..."):
                response = self.client.messages.create(
                    model=Config.MODEL,
                    max_tokens=4000,
                    system=system_prompt,
                    messages=[{"role": "user", "content": f"Create: {user_request}"}]
                )
            
            code = re.sub(r'```(?:openscad)?\n', '', response.content[0].text)
            code = re.sub(r'```\s*$', '', code).strip()
            
            return True, code, "✓ Code generated successfully"
        except Exception as e:
            return False, "", f"Error: {e}"

class ModelAgent:
    def __init__(self, api_key: str):
        self.client = Anthropic(api_key=api_key)
        self.classifier = RequestClassifier(self.client)
        self.generator = ModelGenerator(self.client)
        self.fallbacks = FallbackPatterns()
    
    def process_request(self, user_input: str) -> Dict:
        request_type = self.classifier.classify(user_input)
        
        if request_type == RequestType.ORGANIC:
            return {
                "success": False,
                "scad_code": "",
                "message": "⚠ Organic shapes not suitable for OpenSCAD. Try Blender or ZBrush.",
                "fallback_used": False
            }
        
        fallback = self._check_fallbacks(user_input)
        if fallback:
            return fallback
        
        success, code, message = self.generator.generate(user_input)
        return {
            "success": success,
            "scad_code": code,
            "message": message,
            "fallback_used": False
        }
    
    def _check_fallbacks(self, user_input: str) -> Optional[Dict]:
        lower = user_input.lower()
        
        if "funnel" in lower:
            return {
                "success": True,
                "scad_code": self.fallbacks.funnel(),
                "message": "✓ Funnel template",
                "fallback_used": True
            }
        if "bracket" in lower:
            return {
                "success": True,
                "scad_code": self.fallbacks.bracket(),
                "message": "✓ Bracket template",
                "fallback_used": True
            }
        if any(w in lower for w in ["box", "container"]):
            has_lid = "lid" in lower
            return {
                "success": True,
                "scad_code": self.fallbacks.box(lid=has_lid),
                "message": "✓ Box template",
                "fallback_used": True
            }
        
        return None

# ============================================================================
# MAIN APP
# ============================================================================

def main():
    secrets = load_secrets()
    
    # Title
    st.markdown("<h1 style='text-align: center; text-shadow: 0 0 20px rgba(0,210,255,0.6);'>PROJECT 08</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #aaa;'>Unified Platform: Store Assistant + 3D Model Generator</p>", unsafe_allow_html=True)
    
    # Sidebar
    with st.sidebar:
        st.markdown("### 🎛️ Mode Selection")
        
        mode = st.radio(
            "Choose Mode:",
            ["🛍️ Store Assistant", "🔷 3D Model Generator"],
            label_visibility="collapsed"
        )
        
        st.markdown("---")
        
        # Show products if in store mode
        if mode == "🛍️ Store Assistant":
            st.markdown("### 💎 Collection")
            products = get_inventory(secrets['shopify_api_key'], secrets['shopify_store_url'])
            if products:
                for p in products:
                    st.markdown(f"""
                    <a href="{p['link']}" target="_blank" style="text-decoration:none;">
                        <div class="product-card">
                            <img src="{p['img']}" class="product-img">
                            <div class="card-title">{p['title']}</div>
                            <div class="card-price">${p['price']} 
                                <span class="card-qty">● {p['qty']}</span>
                            </div>
                        </div>
                    </a>
                    """, unsafe_allow_html=True)
            else:
                st.info("Configure Shopify keys in secrets")
        else:
            st.markdown("### 💡 Quick Examples")
            st.markdown("""
            - Create a funnel
            - Make a mounting bracket
            - Design a box with lid
            - Build a phone stand
            """)
        
        st.markdown("---")
        st.markdown("### ⚙️ API Status")
        
        if secrets['google_api_key']:
            st.success("✓ Google API")
        else:
            st.warning("⚠ Google API missing")
        
        if secrets['anthropic_api_key']:
            st.success("✓ Anthropic API")
        else:
            st.warning("⚠ Anthropic API missing")
    
    # Main Content Area
    if mode == "🛍️ Store Assistant":
        render_store_assistant(secrets)
    else:
        render_3d_generator(secrets)

def render_store_assistant(secrets):
    """Render the Shopify store chatbot"""
    
    if not secrets['google_api_key']:
        st.error("⚠ Google API key required. Add to Streamlit secrets.")
        return
    
    # Initialize Gemini
    try:
        client = genai.Client(api_key=secrets['google_api_key'])
        products = get_inventory(secrets['shopify_api_key'], secrets['shopify_store_url'])
    except Exception as e:
        st.error(f"Error initializing store: {e}")
        return
    
    # Initialize chat history
    if "store_messages" not in st.session_state:
        st.session_state.store_messages = [
            {"role": "assistant", "content": "Welcome to Project 08! / ברוכים הבאים"}
        ]
    
    # Display chat history
    for msg in st.session_state.store_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"], unsafe_allow_html=True)
    
    # Chat input
    if prompt := st.chat_input("Ask about products..."):
        st.session_state.store_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        try:
            history = [
                {"role": "user" if m["role"]=="user" else "model", 
                 "parts": [{"text": str(m["content"])}]} 
                for m in st.session_state.store_messages[:-1]
            ]
            
            chat = client.chats.create(
                model="gemini-2.0-flash-exp",
                history=history,
                config=types.GenerateContentConfig(
                    system_instruction=get_store_system_instruction(products),
                    temperature=0.7
                )
            )
            
            with st.spinner("Processing..."):
                response = chat.send_message(prompt)
            
            st.session_state.store_messages.append({"role": "assistant", "content": response.text})
            with st.chat_message("assistant"):
                st.markdown(response.text, unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Error: {e}")

def render_3d_generator(secrets):
    """Render the 3D model generator"""
    
    if not secrets['anthropic_api_key']:
        st.error("⚠ Anthropic API key required. Add to Streamlit secrets.")
        st.markdown("""
        ### How to Add API Key:
        1. Go to Settings → Secrets
        2. Add: `ANTHROPIC_API_KEY = "your-key"`
        3. Get key from: [console.anthropic.com](https://console.anthropic.com/)
        """)
        return
    
    # Initialize generation history
    if '3d_history' not in st.session_state:
        st.session_state['3d_history'] = []
    
    # Input form
    with st.form("model_request"):
        user_input = st.text_area(
            "Describe your 3D model:",
            placeholder="e.g., Create a funnel with 100mm top diameter",
            height=100
        )
        
        col1, col2 = st.columns([1, 5])
        with col1:
            submit = st.form_submit_button("🚀 Generate", use_container_width=True)
        with col2:
            if st.form_submit_button("🗑️ Clear", use_container_width=True):
                st.session_state['3d_history'] = []
                st.rerun()
    
    # Process request
    if submit and user_input:
        try:
            agent = ModelAgent(secrets['anthropic_api_key'])
            result = agent.process_request(user_input)
            
            st.session_state['3d_history'].append({
                "request": user_input,
                "result": result
            })
        except Exception as e:
            st.error(f"Error: {e}")
    
    # Display history
    if st.session_state['3d_history']:
        st.markdown("---")
        st.markdown("## 📜 Generation History")
    
    for idx, item in enumerate(reversed(st.session_state['3d_history'])):
        st.markdown(f"### 📝 Request #{len(st.session_state['3d_history']) - idx}")
        st.markdown(f"*{item['request']}*")
        
        result = item['result']
        
        if result['success']:
            st.markdown(f"""
            <div class="success-box">
                <strong>✅ {result['message']}</strong>
            </div>
            """, unsafe_allow_html=True)
            
            # 3D Preview
            st.markdown("#### 🔷 3D Preview")
            try:
                preview_html = generate_threejs_html(result['scad_code'], height=500)
                components.html(preview_html, height=520, scrolling=False)
            except Exception as e:
                st.warning(f"Preview not available: {e}")
            
            st.markdown("---")
            
            # Code viewer and download
            col1, col2 = st.columns([2, 1])
            
            with col1:
                with st.expander("📄 View OpenSCAD Code", expanded=False):
                    st.code(result['scad_code'], language='javascript')
            
            with col2:
                st.download_button(
                    label="💾 Download .scad",
                    data=result['scad_code'],
                    file_name=f"model_{len(st.session_state['3d_history']) - idx}.scad",
                    mime="text/plain",
                    use_container_width=True
                )
        else:
            st.markdown(f"""
            <div class="error-box">
                <strong>❌ {result['message']}</strong>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("---")

if __name__ == "__main__":
    main()
