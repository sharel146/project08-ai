"""
3D Model Generator - Standalone Version
AI-powered 3D model generation with OpenSCAD and Meshy.ai
"""

import streamlit as st
import streamlit.components.v1 as components
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
# PAGE CONFIGURATION
# ============================================================================

st.set_page_config(
    page_title="AI 3D Model Generator",
    page_icon="🎨",
    layout="wide"
)

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
# 3D PREVIEW GENERATOR
# ============================================================================

def parse_openscad_to_threejs(scad_code: str) -> List[Dict[str, Any]]:
    """Parse OpenSCAD code and extract primitives"""
    objects = []
    code = re.sub(r'//.*', '', scad_code)
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
    
    # Cubes with translate
    for match in re.finditer(r'translate\s*\(\s*\[([^\]]+)\]\s*\)[^c]*cube\s*\(\s*\[([^\]]+)\]', code):
        try:
            pos = [float(x.strip()) for x in match.group(1).split(',')]
            size = [float(x.strip()) for x in match.group(2).split(',')]
            objects.append({'type': 'cube', 'size': size, 'position': pos})
        except: pass
    
    # Standalone cubes
    for match in re.finditer(r'cube\s*\(\s*\[([^\]]+)\]', code):
        try:
            size = [float(x.strip()) for x in match.group(1).split(',')]
            if not any(obj['type'] == 'cube' and obj['size'] == size for obj in objects):
                objects.append({'type': 'cube', 'size': size, 'position': [0, 0, 0]})
        except: pass
    
    # Cylinders and cones
    for match in re.finditer(r'cylinder\s*\([^)]*h\s*=\s*([\d.]+)[^)]*r1\s*=\s*([\d.]+)[^)]*r2\s*=\s*([\d.]+)', code):
        try:
            h, r1, r2 = float(match.group(1)), float(match.group(2)), float(match.group(3))
            objects.append({'type': 'cone', 'height': h, 'radiusTop': r1, 'radiusBottom': r2, 'position': [0, 0, 0]})
        except: pass
    
    return objects if objects else [{'type': 'cube', 'size': [50, 50, 50], 'position': [0, 0, 0]}]


def generate_threejs_html(scad_code: str, height: int = 400) -> str:
    """Generate HTML with Three.js viewer"""
    objects = parse_openscad_to_threejs(scad_code)
    
    return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ margin: 0; overflow: hidden; background: linear-gradient(135deg, #1a1a2e, #16213e); }}
        #viewer {{ width: 100%; height: {height}px; }}
    </style>
</head>
<body>
    <div id="viewer"></div>
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
        const light1 = new THREE.DirectionalLight(0xffffff, 0.8);
        light1.position.set(5, 10, 7);
        scene.add(light1);
        
        const material = new THREE.MeshPhongMaterial({{ color: 0x00d2ff }});
        const modelGroup = new THREE.Group();
        const objects = {objects};
        
        objects.forEach(obj => {{
            let mesh;
            if (obj.type === 'cube') {{
                const geometry = new THREE.BoxGeometry(obj.size[0], obj.size[2], obj.size[1]);
                mesh = new THREE.Mesh(geometry, material);
                mesh.position.set(obj.position[0] + obj.size[0]/2, obj.position[2] + obj.size[2]/2, obj.position[1] + obj.size[1]/2);
            }} else if (obj.type === 'cone') {{
                const geometry = new THREE.CylinderGeometry(obj.radiusTop, obj.radiusBottom, obj.height, 32);
                mesh = new THREE.Mesh(geometry, material);
                mesh.position.set(0, obj.height/2, 0);
            }}
            if (mesh) modelGroup.add(mesh);
        }});
        
        scene.add(modelGroup);
        
        const box = new THREE.Box3().setFromObject(modelGroup);
        const center = box.getCenter(new THREE.Vector3());
        const size = box.getSize(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z);
        camera.position.set(maxDim * 1.5, maxDim, maxDim * 1.5);
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
        
        function animate() {{
            requestAnimationFrame(animate);
            if (!isDragging) modelGroup.rotation.y += 0.005;
            renderer.render(scene, camera);
        }}
        animate();
    </script>
</body>
</html>
"""


# ============================================================================
# PROMPT ENHANCEMENT
# ============================================================================

class PromptEnhancer:
    def __init__(self, client: Anthropic):
        self.client = client
    
    def enhance(self, prompt: str, type_hint: str) -> str:
        if len(prompt.strip()) >= 15:
            return prompt
        
        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=60,
                messages=[{"role": "user", "content": f'Improve this 3D {type_hint} prompt to be clear but UNDER 50 words: "{prompt}". Respond ONLY with the improved prompt.'}]
            )
            enhanced = response.content[0].text.strip().strip('"').strip("'")
            if len(enhanced) > 200:
                enhanced = enhanced[:200]
            return enhanced
        except:
            return f"{prompt} detailed 3D printable model"


# ============================================================================
# AI MESH GENERATION (Multi-Provider)
# ============================================================================

class MeshProvider(Enum):
    MESHY = "meshy"
    RODIN = "rodin"


class OrganicMeshGenerator:
    def __init__(self, anthropic_client: Anthropic, meshy_key: Optional[str] = None, rodin_key: Optional[str] = None):
        self.anthropic_client = anthropic_client
        self.meshy_key = meshy_key
        self.rodin_key = rodin_key
        self.enhancer = PromptEnhancer(anthropic_client)
    
    def select_provider(self, prompt: str) -> MeshProvider:
        """Smart provider selection based on prompt"""
        lower = prompt.lower()
        
        # Rodin is better for: cartoons, stylized, simple characters
        if any(word in lower for word in ['cartoon', 'stylized', 'simple', 'cute', 'toy']):
            if self.rodin_key:
                return MeshProvider.RODIN
        
        # Meshy is better for: realistic, detailed, complex
        # Default to Meshy if available, otherwise Rodin
        if self.meshy_key:
            return MeshProvider.MESHY
        elif self.rodin_key:
            return MeshProvider.RODIN
        
        return None
    
    def generate(self, user_request: str) -> Dict:
        enhanced_prompt = self.enhancer.enhance(user_request, "organic")
        
        if enhanced_prompt != user_request:
            st.success(f"💡 Enhanced: \"{enhanced_prompt}\"")
        
        # Select best provider
        provider = self.select_provider(enhanced_prompt)
        
        if not provider:
            return {"success": False, "message": "⚠️ Add MESHY_API_KEY or RODIN_API_KEY to secrets", "stl_data": None}
        
        if provider == MeshProvider.MESHY:
            st.info("🎨 Using Meshy.ai (best for realistic shapes)")
            return self._generate_with_meshy(enhanced_prompt)
        else:
            st.info("🎨 Using Rodin AI (best for cartoon/stylized)")
            return self._generate_with_rodin(enhanced_prompt)
    
    def _generate_with_meshy(self, prompt: str) -> Dict:
        try:
            response = requests.post(
                "https://api.meshy.ai/v2/text-to-3d",
                headers={"Authorization": f"Bearer {self.meshy_key}", "Content-Type": "application/json"},
                json={
                    "mode": "preview",
                    "prompt": prompt,
                    "art_style": "sculpture",
                    "negative_prompt": "low quality, blurry, disconnected parts",
                    "ai_model": "meshy-4"
                },
                timeout=10
            )
            
            if response.status_code not in [200, 202]:
                return {"success": False, "message": f"❌ API error {response.status_code}", "stl_data": None}
            
            task_id = response.json().get("result") or response.json().get("id")
            if not task_id:
                return {"success": False, "message": "❌ No task ID", "stl_data": None}
            
            progress_bar = st.progress(0)
            
            for i in range(40):
                status_response = requests.get(
                    f"https://api.meshy.ai/v2/text-to-3d/{task_id}",
                    headers={"Authorization": f"Bearer {self.meshy_key}"}
                )
                
                if status_response.status_code != 200:
                    return {"success": False, "message": "❌ Status check failed", "stl_data": None}
                
                status_data = status_response.json()
                status = status_data.get("status")
                
                if status == "SUCCEEDED":
                    progress_bar.progress(100)
                    glb_url = status_data.get("model_urls", {}).get("glb")
                    
                    if glb_url:
                        model_data = requests.get(glb_url).content
                        return {
                            "success": True,
                            "message": "✓ Generated with Meshy.ai ($0.25)",
                            "stl_data": model_data,
                            "file_format": "glb",
                            "provider": "Meshy.ai"
                        }
                    else:
                        return {"success": False, "message": "❌ No model file", "stl_data": None}
                        
                elif status == "FAILED":
                    error_msg = status_data.get("error", "Unknown error")
                    return {"success": False, "message": f"❌ Failed: {error_msg}", "stl_data": None}
                
                progress = status_data.get("progress", 0)
                progress_bar.progress(min(progress, 99))
                time.sleep(3)
            
            return {"success": False, "message": "❌ Timeout", "stl_data": None}
            
        except Exception as e:
            return {"success": False, "message": f"❌ Error: {e}", "stl_data": None}
    
    def _generate_with_rodin(self, prompt: str) -> Dict:
        """Generate using Rodin AI - faster, good for cartoons"""
        try:
            response = requests.post(
                "https://hyperhuman.deemos.com/api/v2/rodin",
                headers={
                    "Authorization": f"Bearer {self.rodin_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "prompt": prompt,
                    "tier": "standard"  # Fast generation
                },
                timeout=10
            )
            
            if response.status_code not in [200, 201]:
                # If Rodin fails, fallback to Meshy if available
                if self.meshy_key:
                    st.warning("⚠️ Rodin failed, trying Meshy.ai...")
                    return self._generate_with_meshy(prompt)
                return {"success": False, "message": f"❌ API error {response.status_code}", "stl_data": None}
            
            task_uuid = response.json().get("uuid")
            if not task_uuid:
                return {"success": False, "message": "❌ No task ID", "stl_data": None}
            
            progress_bar = st.progress(0)
            
            # Rodin is usually faster - 30 second timeout
            for i in range(20):
                status_response = requests.get(
                    f"https://hyperhuman.deemos.com/api/v2/rodin/{task_uuid}",
                    headers={"Authorization": f"Bearer {self.rodin_key}"}
                )
                
                if status_response.status_code != 200:
                    return {"success": False, "message": "❌ Status check failed", "stl_data": None}
                
                status_data = status_response.json()
                status = status_data.get("status")
                
                if status == "success":
                    progress_bar.progress(100)
                    model_url = status_data.get("model_url")
                    
                    if model_url:
                        model_data = requests.get(model_url).content
                        return {
                            "success": True,
                            "message": "✓ Generated with Rodin AI ($0.15)",
                            "stl_data": model_data,
                            "file_format": "glb",
                            "provider": "Rodin AI"
                        }
                    else:
                        return {"success": False, "message": "❌ No model file", "stl_data": None}
                        
                elif status == "failed":
                    # Fallback to Meshy if available
                    if self.meshy_key:
                        st.warning("⚠️ Rodin failed, trying Meshy.ai...")
                        return self._generate_with_meshy(prompt)
                    return {"success": False, "message": "❌ Generation failed", "stl_data": None}
                
                progress = min((i + 1) * 5, 95)  # Estimate progress
                progress_bar.progress(progress)
                time.sleep(1.5)  # Rodin is faster, check more frequently
            
            return {"success": False, "message": "❌ Timeout", "stl_data": None}
            
        except Exception as e:
            # Fallback to Meshy on any error
            if self.meshy_key:
                st.warning(f"⚠️ Rodin error: {e}. Trying Meshy.ai...")
                return self._generate_with_meshy(prompt)
            return {"success": False, "message": f"❌ Error: {e}", "stl_data": None}


# ============================================================================
# OPENSCAD CLASSES
# ============================================================================

class Config:
    MODEL = "claude-sonnet-4-20250514"
    MAX_CORRECTION_ATTEMPTS = 5
    BUILD_VOLUME = {"x": 256, "y": 256, "z": 256}


class RequestType(Enum):
    FUNCTIONAL = "functional"
    ORGANIC = "organic"


class RequestClassifier:
    def __init__(self, client: Anthropic):
        self.client = client
    
    def classify(self, user_request: str) -> RequestType:
        prompt = f"""Is this request for FUNCTIONAL (geometric parts) or ORGANIC (animals/curved shapes)?
"{user_request}"
Respond with ONLY: FUNCTIONAL or ORGANIC"""

        try:
            response = self.client.messages.create(
                model=Config.MODEL,
                max_tokens=10,
                messages=[{"role": "user", "content": prompt}]
            )
            
            classification = response.content[0].text.strip().upper()
            return RequestType.ORGANIC if "ORGANIC" in classification else RequestType.FUNCTIONAL
        except:
            return RequestType.FUNCTIONAL


class ModelGenerator:
    def __init__(self, client: Anthropic):
        self.client = client
        self.enhancer = PromptEnhancer(client)
    
    def generate(self, user_request: str) -> Tuple[bool, str, str]:
        enhanced = self.enhancer.enhance(user_request, "functional")
        
        if enhanced != user_request:
            st.success(f"💡 Enhanced: \"{enhanced}\"")
        
        system_prompt = f"""Expert OpenSCAD programmer.
BUILD: {Config.BUILD_VOLUME['x']}mm cube
Respond with ONLY valid OpenSCAD code, no explanations."""
        
        try:
            response = self.client.messages.create(
                model=Config.MODEL,
                max_tokens=4000,
                system=system_prompt,
                messages=[{"role": "user", "content": f"Create: {enhanced}"}]
            )
            
            code = re.sub(r'```(?:openscad)?\n', '', response.content[0].text)
            code = re.sub(r'```\s*$', '', code).strip()
            
            return True, code, "✓ Generated"
        except Exception as e:
            return False, "", f"Error: {e}"


class FallbackPatterns:
    @staticmethod
    def funnel() -> str:
        return """difference() {
    cylinder(h=80, r1=50, r2=10, $fn=100);
    translate([0, 0, 2])
        cylinder(h=80, r1=48, r2=8, $fn=100);
}"""
    
    @staticmethod
    def bracket() -> str:
        return """difference() {
    union() {
        cube([5, 50, 40]);
        cube([50, 50, 5]);
    }
    translate([2.5, 12.5, 20])
        rotate([0, 90, 0])
        cylinder(h=10, r=2.5, $fn=30);
}"""


class ModelAgent:
    def __init__(self, anthropic_key: str, meshy_key: Optional[str] = None, rodin_key: Optional[str] = None):
        self.client = Anthropic(api_key=anthropic_key)
        self.classifier = RequestClassifier(self.client)
        self.generator = ModelGenerator(self.client)
        self.fallbacks = FallbackPatterns()
        self.mesh_generator = OrganicMeshGenerator(self.client, meshy_key, rodin_key)
    
    def process_request(self, user_input: str) -> Dict:
        request_type = self.classifier.classify(user_input)
        
        if request_type == RequestType.ORGANIC:
            result = self.mesh_generator.generate(user_input)
            result['is_mesh'] = True
            return result
        
        # Check fallbacks
        lower = user_input.lower()
        if "funnel" in lower:
            return {"success": True, "scad_code": self.fallbacks.funnel(), "message": "✓ Funnel", "is_mesh": False}
        if "bracket" in lower:
            return {"success": True, "scad_code": self.fallbacks.bracket(), "message": "✓ Bracket", "is_mesh": False}
        
        success, code, message = self.generator.generate(user_input)
        return {"success": success, "scad_code": code, "message": message, "is_mesh": False}


# ============================================================================
# MAIN APP
# ============================================================================

def main():
    st.title("🎨 AI 3D Model Generator")
    st.markdown("*Create functional parts and organic shapes*")
    
    # Load API keys
    try:
        anthropic_key = st.secrets.get("ANTHROPIC_API_KEY", "")
        meshy_key = st.secrets.get("MESHY_API_KEY", "")
        rodin_key = st.secrets.get("RODIN_API_KEY", "")
    except:
        anthropic_key = ""
        meshy_key = ""
        rodin_key = ""
    
    if not anthropic_key:
        st.error("⚠️ Add ANTHROPIC_API_KEY to Streamlit secrets")
        return
    
    # Show available providers
    providers_available = []
    if meshy_key:
        providers_available.append("Meshy.ai ($0.25)")
    if rodin_key:
        providers_available.append("Rodin AI ($0.15)")
    
    if providers_available:
        st.sidebar.success(f"🎨 Providers: {', '.join(providers_available)}")
    else:
        st.sidebar.warning("⚠️ Add MESHY_API_KEY or RODIN_API_KEY for organic shapes")
    
    # Initialize history
    if 'history' not in st.session_state:
        st.session_state['history'] = []
    
    # Input form
    with st.form("model_request"):
        user_input = st.text_area(
            "What do you want to create?",
            placeholder="Try: simple vase, cartoon bear, mounting bracket...",
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
            agent = ModelAgent(anthropic_key, meshy_key, rodin_key)
            result = agent.process_request(user_input)
            st.session_state['history'].append({"request": user_input, "result": result})
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
                st.markdown(f"""<div class="success-box"><strong>✅ {result['message']}</strong></div>""", unsafe_allow_html=True)
                
                if result.get('is_mesh'):
                    # AI Mesh
                    provider_name = result.get('provider', 'AI')
                    st.success(f"✨ Generated with **{provider_name}**")
                    
                    if result.get('stl_data'):
                        file_format = result.get('file_format', 'glb')
                        st.download_button(
                            label=f"💾 Download .{file_format} file",
                            data=result['stl_data'],
                            file_name=f"model_{len(st.session_state['history']) - idx}.{file_format}",
                            mime="application/octet-stream",
                            use_container_width=True
                        )
                        if file_format == 'glb':
                            st.info("🔄 Convert to STL: https://products.aspose.app/3d/conversion/glb-to-stl")
                else:
                    # OpenSCAD
                    try:
                        preview_html = generate_threejs_html(result['scad_code'], height=400)
                        components.html(preview_html, height=420, scrolling=False)
                    except: pass
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.download_button(
                            label="💾 Download .scad file",
                            data=result['scad_code'],
                            file_name=f"model_{len(st.session_state['history']) - idx}.scad",
                            mime="text/plain",
                            use_container_width=True
                        )
                    
                    with col2:
                        # Also provide as TXT for mobile viewing
                        st.download_button(
                            label="📱 Download as .txt (for mobile)",
                            data=result['scad_code'],
                            file_name=f"model_{len(st.session_state['history']) - idx}.txt",
                            mime="text/plain",
                            use_container_width=True
                        )
                    
                    # Show code inline for mobile users
                    with st.expander("👀 View Code (click to expand)"):
                        st.code(result['scad_code'], language='javascript')
                        st.info("💡 Copy this code and paste it into OpenSCAD on your computer to generate the STL file")
            else:
                st.markdown(f"""<div class="error-box"><strong>❌ {result['message']}</strong></div>""", unsafe_allow_html=True)
            
            st.markdown("---")


if __name__ == "__main__":
    main()
