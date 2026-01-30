"""
PROJECT 08 - Unified Platform (PRODUCTION VERSION)
Clean UI with automatic prompt enhancement
"""

import streamlit as st
import streamlit.components.v1 as components
from google import genai
from google.genai import types
import requests
import subprocess
import re
import os
import time
import json
from anthropic import Anthropic
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum

# ============================================================================
# 3D PREVIEW GENERATOR
# ============================================================================

def parse_openscad_to_threejs(scad_code: str) -> List[Dict[str, Any]]:
    """Parse OpenSCAD code and extract primitives WITH their transformations"""
    objects = []
    code = re.sub(r'//.*', '', scad_code)
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
    
    # Find all translate + cube combinations
    translate_cube_pattern = r'translate\s*\(\s*\[([^\]]+)\]\s*\)[^c]*cube\s*\(\s*\[([^\]]+)\]'
    for match in re.finditer(translate_cube_pattern, code):
        try:
            pos = [float(x.strip()) for x in match.group(1).split(',')]
            size = [float(x.strip()) for x in match.group(2).split(',')]
            objects.append({'type': 'cube', 'size': size, 'position': pos})
        except:
            pass
    
    # Standalone cubes
    all_cubes = list(re.finditer(r'cube\s*\(\s*\[([^\]]+)\]', code))
    for match in all_cubes:
        try:
            size = [float(x.strip()) for x in match.group(1).split(',')]
            if not any(obj['type'] == 'cube' and obj['size'] == size for obj in objects):
                objects.append({'type': 'cube', 'size': size, 'position': [0, 0, 0]})
        except:
            pass
    
    # Cones with translate
    translate_cone_pattern = r'translate\s*\(\s*\[([^\]]+)\]\s*\)[^c]*cylinder\s*\([^)]*h\s*=\s*([\d.]+)[^)]*r1\s*=\s*([\d.]+)[^)]*r2\s*=\s*([\d.]+)'
    for match in re.finditer(translate_cone_pattern, code):
        try:
            pos = [float(x.strip()) for x in match.group(1).split(',')]
            h, r1, r2 = float(match.group(2)), float(match.group(3)), float(match.group(4))
            objects.append({'type': 'cone', 'height': h, 'radiusTop': r1, 'radiusBottom': r2, 'position': pos})
        except:
            pass
    
    # Standalone cones
    cone_pattern = r'cylinder\s*\([^)]*h\s*=\s*([\d.]+)[^)]*r1\s*=\s*([\d.]+)[^)]*r2\s*=\s*([\d.]+)'
    for match in re.finditer(cone_pattern, code):
        match_text = code[max(0, match.start()-50):match.start()]
        if 'translate' not in match_text:
            try:
                h, r1, r2 = float(match.group(1)), float(match.group(2)), float(match.group(3))
                objects.append({'type': 'cone', 'height': h, 'radiusTop': r1, 'radiusBottom': r2, 'position': [0, 0, 0]})
            except:
                pass
    
    # Cylinders with translate
    translate_cylinder_pattern = r'translate\s*\(\s*\[([^\]]+)\]\s*\)[^c]*cylinder\s*\([^)]*h\s*=\s*([\d.]+)[^)]*r\s*=\s*([\d.]+)'
    for match in re.finditer(translate_cylinder_pattern, code):
        try:
            pos = [float(x.strip()) for x in match.group(1).split(',')]
            h, r = float(match.group(2)), float(match.group(3))
            objects.append({'type': 'cylinder', 'height': h, 'radius': r, 'position': pos})
        except:
            pass
    
    # Standalone cylinders
    cylinder_pattern = r'cylinder\s*\([^)]*h\s*=\s*([\d.]+)[^)]*r\s*=\s*([\d.]+)(?![^)]*r[12])'
    for match in re.finditer(cylinder_pattern, code):
        match_text = code[max(0, match.start()-50):match.start()]
        if 'translate' not in match_text and 'r1' not in match.group(0):
            try:
                h, r = float(match.group(1)), float(match.group(2))
                objects.append({'type': 'cylinder', 'height': h, 'radius': r, 'position': [0, 0, 0]})
            except:
                pass
    
    return objects if objects else [{'type': 'cube', 'size': [50, 50, 50], 'position': [0, 0, 0]}]


def generate_threejs_html(scad_code: str, height: int = 500) -> str:
    """Generate HTML with Three.js viewer"""
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
        
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
        scene.add(ambientLight);
        const directionalLight1 = new THREE.DirectionalLight(0xffffff, 0.8);
        directionalLight1.position.set(5, 10, 7);
        scene.add(directionalLight1);
        const directionalLight2 = new THREE.DirectionalLight(0x00d2ff, 0.3);
        directionalLight2.position.set(-5, -10, -7);
        scene.add(directionalLight2);
        
        const material = new THREE.MeshPhongMaterial({{ color: 0x00d2ff, specular: 0x111111, shininess: 30 }});
        const edgeMaterial = new THREE.LineBasicMaterial({{ color: 0x0088cc }});
        
        const modelGroup = new THREE.Group();
        const objects = {objects};
        
        objects.forEach(obj => {{
            let mesh;
            if (obj.type === 'cube') {{
                const geometry = new THREE.BoxGeometry(obj.size[0], obj.size[2], obj.size[1]);
                mesh = new THREE.Mesh(geometry, material);
                const edges = new THREE.EdgesGeometry(geometry);
                mesh.add(new THREE.LineSegments(edges, edgeMaterial));
                mesh.position.set(obj.position[0] + obj.size[0]/2, obj.position[2] + obj.size[2]/2, obj.position[1] + obj.size[1]/2);
            }} else if (obj.type === 'cone') {{
                const geometry = new THREE.CylinderGeometry(obj.radiusTop, obj.radiusBottom, obj.height, 32);
                mesh = new THREE.Mesh(geometry, material);
                const edges = new THREE.EdgesGeometry(geometry);
                mesh.add(new THREE.LineSegments(edges, edgeMaterial));
                mesh.position.set(obj.position[0], obj.position[2] + obj.height/2, obj.position[1]);
            }} else if (obj.type === 'cylinder') {{
                const geometry = new THREE.CylinderGeometry(obj.radius, obj.radius, obj.height, 32);
                mesh = new THREE.Mesh(geometry, material);
                const edges = new THREE.EdgesGeometry(geometry);
                mesh.add(new THREE.LineSegments(edges, edgeMaterial));
                mesh.position.set(obj.position[0], obj.position[2] + obj.height/2, obj.position[1]);
            }}
            if (mesh) modelGroup.add(mesh);
        }});
        
        scene.add(modelGroup);
        
        const box = new THREE.Box3().setFromObject(modelGroup);
        const center = box.getCenter(new THREE.Vector3());
        const size = box.getSize(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z);
        const fov = camera.fov * (Math.PI / 180);
        let cameraZ = Math.abs(maxDim / 2 / Math.tan(fov / 2)) * 2.5;
        camera.position.set(cameraZ, cameraZ * 0.7, cameraZ);
        camera.lookAt(center);
        
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
        renderer.domElement.addEventListener('wheel', (e) => {{
            e.preventDefault();
            camera.position.multiplyScalar(e.deltaY > 0 ? 1.1 : 0.9);
        }});
        
        let autoRotate = true;
        renderer.domElement.addEventListener('mouseenter', () => {{ autoRotate = false; }});
        renderer.domElement.addEventListener('mouseleave', () => {{ autoRotate = true; }});
        
        function animate() {{
            requestAnimationFrame(animate);
            if (autoRotate) modelGroup.rotation.y += 0.005;
            renderer.render(scene, camera);
        }}
        animate();
        
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
# PROMPT ENHANCEMENT ENGINE
# ============================================================================

class PromptEnhancer:
    """Automatically improves user prompts for better AI generation"""
    
    def __init__(self, anthropic_client: Anthropic):
        self.client = anthropic_client
    
    def enhance(self, user_prompt: str, request_type: str) -> str:
        """Enhance a user prompt for better results"""
        
        # Quick enhancement for very short prompts
        if len(user_prompt.strip()) < 15:
            enhancement_prompt = f"""Improve this 3D model prompt for better AI generation results.

USER PROMPT: "{user_prompt}"
REQUEST TYPE: {request_type}

Create a detailed, specific prompt that will generate a high-quality 3D printable model.

Rules:
- Add relevant descriptive details
- Include style keywords (realistic, cartoon, smooth, detailed, etc.)
- Mention "3D printable" or "figurine" if appropriate
- Keep it under 100 characters
- Make it specific and clear

Respond with ONLY the improved prompt, no explanation."""

            try:
                response = self.client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=150,
                    messages=[{"role": "user", "content": enhancement_prompt}]
                )
                
                enhanced = response.content[0].text.strip()
                # Remove quotes if present
                enhanced = enhanced.strip('"').strip("'")
                
                return enhanced
                
            except:
                # Fallback: basic enhancement
                if request_type == "organic":
                    return f"{user_prompt} figurine, detailed, 3D printable"
                else:
                    return f"{user_prompt}, functional part"
        
        return user_prompt


# ============================================================================
# AI MESH GENERATION
# ============================================================================

class OrganicMeshGenerator:
    """Generates organic 3D models using AI with prompt enhancement"""
    
    def __init__(self, anthropic_client: Anthropic, meshy_key: Optional[str] = None):
        self.anthropic_client = anthropic_client
        self.meshy_key = meshy_key
        self.enhancer = PromptEnhancer(anthropic_client)
    
    def generate(self, user_request: str) -> Dict:
        """Generate organic 3D model with automatic prompt enhancement"""
        
        # Enhance the prompt
        with st.spinner("✨ Optimizing your prompt..."):
            enhanced_prompt = self.enhancer.enhance(user_request, "organic")
        
        if enhanced_prompt != user_request:
            st.success(f"💡 Enhanced: \"{enhanced_prompt}\"")
        
        if not self.meshy_key:
            return {
                "success": False,
                "message": "⚠️ Add MESHY_API_KEY to secrets",
                "stl_data": None
            }
        
        return self._generate_with_meshy(enhanced_prompt)
    
    def _generate_with_meshy(self, prompt: str) -> Dict:
        """Generate using Meshy.ai"""
        
        try:
            response = requests.post(
                "https://api.meshy.ai/v2/text-to-3d",
                headers={
                    "Authorization": f"Bearer {self.meshy_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "mode": "preview",
                    "prompt": prompt,
                    "art_style": "realistic",
                    "negative_prompt": "low quality, blurry, distorted",
                    "ai_model": "meshy-4"
                },
                timeout=10
            )
            
            if response.status_code not in [200, 202]:
                return {"success": False, "message": f"❌ API error {response.status_code}", "stl_data": None}
            
            response_data = response.json()
            task_id = response_data.get("result") or response_data.get("id")
            
            if not task_id:
                return {"success": False, "message": "❌ No task ID", "stl_data": None}
            
            # Poll for completion
            progress_bar = st.progress(0)
            
            for i in range(40):
                status_response = requests.get(
                    f"https://api.meshy.ai/v2/text-to-3d/{task_id}",
                    headers={"Authorization": f"Bearer {self.meshy_key}"}
                )
                
                if status_response.status_code != 200:
                    return {"success": False, "message": f"❌ Status check failed", "stl_data": None}
                
                status_data = status_response.json()
                status = status_data.get("status")
                
                if status == "SUCCEEDED":
                    progress_bar.progress(100)
                    
                    model_urls = status_data.get("model_urls", {})
                    glb_url = model_urls.get("glb")
                    
                    if glb_url:
                        model_data = requests.get(glb_url).content
                        return {
                            "success": True,
                            "message": "✓ Generated successfully",
                            "stl_data": model_data,
                            "provider": "Meshy.ai",
                            "file_format": "glb"
                        }
                    else:
                        return {"success": False, "message": "❌ No model file", "stl_data": None}
                        
                elif status == "FAILED":
                    return {"success": False, "message": "❌ Generation failed", "stl_data": None}
                
                progress = status_data.get("progress", 0)
                progress_bar.progress(min(progress, 99))
                time.sleep(3)
            
            return {"success": False, "message": "❌ Timeout", "stl_data": None}
            
        except Exception as e:
            return {"success": False, "message": f"❌ Error: {e}", "stl_data": None}


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


class RequestClassifier:
    def __init__(self, client: Anthropic):
        self.client = client
    
    def classify(self, user_request: str) -> RequestType:
        prompt = f"""Classify this 3D modeling request:

"{user_request}"

Is this:
- FUNCTIONAL: Geometric parts (brackets, boxes, tools, mechanical parts)
- ORGANIC: Natural/curved shapes (animals, people, sculptures, faces)

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
            else:
                return RequestType.UNKNOWN
                
        except:
            return RequestType.UNKNOWN


class ModelGenerator:
    def __init__(self, client: Anthropic):
        self.client = client
        self.enhancer = PromptEnhancer(client)
    
    def generate(self, user_request: str) -> Tuple[bool, str, str]:
        # Enhance prompt
        enhanced_prompt = self.enhancer.enhance(user_request, "functional")
        
        if enhanced_prompt != user_request:
            st.success(f"💡 Enhanced: \"{enhanced_prompt}\"")
        
        system_prompt = f"""Expert OpenSCAD programmer for Bambu Lab A1.
BUILD: {Config.BUILD_VOLUME['x']}mm cube
RULES: Valid code only, $fn>=50, wall>=1.2mm, no explanations.
RESPOND WITH CODE ONLY."""
        
        try:
            response = self.client.messages.create(
                model=Config.MODEL,
                max_tokens=4000,
                system=system_prompt,
                messages=[{"role": "user", "content": f"Create: {enhanced_prompt}"}]
            )
            
            code = re.sub(r'```(?:openscad)?\n', '', response.content[0].text)
            code = re.sub(r'```\s*$', '', code).strip()
            
            return True, code, "✓ Code generated successfully"
        except Exception as e:
            return False, "", f"Error: {e}"


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
    cylinder(h=height, r1=top_d/2, r2=bottom_d/2, $fn=100);
    translate([0, 0, wall])
        cylinder(h=height, r1=(top_d/2)-wall, r2=(bottom_d/2)-wall, $fn=100);
    translate([0, 0, -1])
        cylinder(h=wall+2, r=(bottom_d/2)-wall, $fn=50);
}}

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
    translate([thick/2, width/4, height/2])
        rotate([0, 90, 0])
        cylinder(h=thick*2, r=hole_d/2, center=true, $fn=30);
    translate([width/2, width/4, -thick])
        cylinder(h=thick*3, r=hole_d/2, $fn=30);
}}
"""
    
    @staticmethod
    def box(length: float = 50, width: float = 50, height: float = 30,
            wall_thickness: float = 2, lid: bool = False) -> str:
        code = f"""// Storage Box
length = {length};
width = {width};
height = {height};
wall = {wall_thickness};

difference() {{
    cube([length, width, height]);
    translate([wall, wall, wall])
        cube([length-2*wall, width-2*wall, height]);
}}
"""
        if lid:
            code += f"""
translate([0, width+5, 0])
cube([length, width, wall]);
"""
        return code


class ModelAgent:
    def __init__(self, api_key: str, meshy_key: Optional[str] = None):
        self.client = Anthropic(api_key=api_key)
        self.classifier = RequestClassifier(self.client)
        self.generator = ModelGenerator(self.client)
        self.fallbacks = FallbackPatterns()
        self.mesh_generator = OrganicMeshGenerator(self.client, meshy_key)
    
    def process_request(self, user_input: str) -> Dict:
        request_type = self.classifier.classify(user_input)
        
        if request_type == RequestType.ORGANIC:
            result = self.mesh_generator.generate(user_input)
            result['request_type'] = 'organic'
            result['is_mesh'] = True
            return result
        
        fallback = self._check_fallbacks(user_input)
        if fallback:
            return fallback
        
        success, code, message = self.generator.generate(user_input)
        return {
            "success": success,
            "scad_code": code,
            "message": message,
            "fallback_used": False,
            "is_mesh": False
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
# PAGE CONFIGURATION
# ============================================================================

st.set_page_config(
    page_title="3D Model Generator",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Minimal CSS
st.markdown("""
<style>
    .stApp {
        background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
        color: #fff;
    }
    .success-box {
        background: rgba(0, 255, 127, 0.1);
        border: 1px solid rgba(0, 255, 127, 0.3);
        border-radius: 8px;
        padding: 15px;
        margin: 10px 0;
    }
    .error-box {
        background: rgba(255, 0, 0, 0.1);
        border: 1px solid rgba(255, 0, 0, 0.3);
        border-radius: 8px;
        padding: 15px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# SECRETS LOADING
# ============================================================================

def load_secrets():
    secrets = {}
    try:
        secrets['anthropic_api_key'] = st.secrets.get("ANTHROPIC_API_KEY", "")
        secrets['meshy_api_key'] = st.secrets.get("MESHY_API_KEY", "")
    except:
        secrets['anthropic_api_key'] = ""
        secrets['meshy_api_key'] = ""
    return secrets


# ============================================================================
# MAIN APP
# ============================================================================

def main():
    st.title("🎨 AI 3D Model Generator")
    st.markdown("*Create functional parts and organic shapes*")
    
    secrets = load_secrets()
    
    if not secrets['anthropic_api_key']:
        st.error("⚠ Add ANTHROPIC_API_KEY to secrets")
        return
    
    # Initialize history
    if 'history' not in st.session_state:
        st.session_state['history'] = []
    
    # Input form
    with st.form("model_request"):
        user_input = st.text_area(
            "What do you want to create?",
            placeholder="Examples: dog figurine, mounting bracket, storage box...",
            height=80
        )
        
        col1, col2 = st.columns([1, 5])
        with col1:
            submit = st.form_submit_button("🚀 Generate", use_container_width=True)
        with col2:
            if st.form_submit_button("🗑️ Clear", use_container_width=True):
                st.session_state['history'] = []
                st.rerun()
    
    # Process request
    if submit and user_input:
        try:
            agent = ModelAgent(secrets['anthropic_api_key'], secrets.get('meshy_api_key'))
            result = agent.process_request(user_input)
            
            st.session_state['history'].append({
                "request": user_input,
                "result": result
            })
            
        except Exception as e:
            st.error(f"Error: {e}")
    
    # Display history
    if st.session_state['history']:
        st.markdown("---")
        st.markdown("## 📋 Generation History")
        
        for idx, item in enumerate(reversed(st.session_state['history'])):
            st.markdown(f"### Request #{len(st.session_state['history']) - idx}")
            st.markdown(f"*{item['request']}*")
            
            result = item['result']
            
            if result['success']:
                st.markdown(f"""
                <div class="success-box">
                    <strong>✅ {result['message']}</strong>
                </div>
                """, unsafe_allow_html=True)
                
                is_mesh = result.get('is_mesh', False)
                
                if is_mesh:
                    # AI Mesh
                    if result.get('stl_data'):
                        file_format = result.get('file_format', 'glb')
                        
                        st.download_button(
                            label=f"💾 Download .{file_format} file",
                            data=result['stl_data'],
                            file_name=f"model_{len(st.session_state['history']) - idx}.{file_format}",
                            mime="application/octet-stream",
                            use_container_width=True
                        )
                else:
                    # OpenSCAD
                    try:
                        preview_html = generate_threejs_html(result['scad_code'], height=400)
                        components.html(preview_html, height=420, scrolling=False)
                    except:
                        pass
                    
                    st.download_button(
                        label="💾 Download .scad file",
                        data=result['scad_code'],
                        file_name=f"model_{len(st.session_state['history']) - idx}.scad",
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
