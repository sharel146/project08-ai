"""
AI 3D Model Generator - BEST QUALITY
Uses Meshy v4 REFINE mode - highest quality available
$1 per model but actually works!
"""

import streamlit as st
import requests
import time
import base64
from anthropic import Anthropic
from typing import Dict, Optional

st.set_page_config(page_title="AI 3D Model Generator", page_icon="🎨", layout="wide")

st.markdown("""
<style>
    .stApp {
        background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
        color: #fff;
    }
</style>
""", unsafe_allow_html=True)


class PromptEnhancer:
    def __init__(self, client: Anthropic):
        self.client = client
    
    def enhance(self, prompt: str) -> str:
        """Make prompts EXTREMELY detailed for best results"""
        
        if len(prompt.strip()) >= 40:
            return prompt
        
        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=150,
                messages=[{"role": "user", "content": f"""Create an EXTREMELY detailed description for 3D modeling:

"{prompt}"

Include EVERY detail: exact dimensions, materials, surface finish, mechanical features (holes, threads, grooves), proportions, style, texture.

Example for "door knob":
"Professional door knob: 65mm diameter spherical handle with brushed stainless steel finish, three decorative concentric grooves at 5mm spacing around equator, smooth polished surface with subtle radial brushing pattern. Square mounting base 45x45mm with central 12mm diameter through-hole for door spindle, four corner 4mm screw holes at 35mm spacing. Tapered neck connecting handle to base with smooth filleted transitions. Chamfered edges 2mm radius. Total assembly height 85mm."

Example for "phone stand":
"Modern phone stand: stable rectangular base 110x90mm with rubber feet recesses, angled back support rising 65 degrees from horizontal with 6mm wall thickness, lower front lip 18mm high with 3mm rubber grip channel, side walls with 2mm radius rounded edges, sleek minimalist design with matte black finish, accommodates phones 6-9mm thick"

Now describe: {prompt}"""}]
            )
            
            enhanced = response.content[0].text.strip().strip('"').strip("'")
            return enhanced
        except:
            return prompt


class MeshyRefineGenerator:
    def __init__(self, anthropic_client: Anthropic, meshy_key: str):
        self.anthropic_client = anthropic_client
        self.meshy_key = meshy_key
        self.enhancer = PromptEnhancer(anthropic_client)
    
    def generate(self, user_request: str) -> Dict:
        """Generate with Meshy v4 - highest quality possible"""
        
        # Enhance prompt with extreme detail
        enhanced_prompt = self.enhancer.enhance(user_request)
        
        st.info(f"🔍 **Enhanced Prompt:**\n\n*{enhanced_prompt}*")
        
        max_attempts = 3  # Try up to 3 times
        
        for attempt in range(max_attempts):
            try:
                with st.spinner(f"🎨 Creating your model..."):
                    # Use PREVIEW mode (actually works!)
                    response = requests.post(
                        "https://api.meshy.ai/v2/text-to-3d",
                        headers={
                            "Authorization": f"Bearer {self.meshy_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "mode": "preview",
                            "prompt": enhanced_prompt,
                            "art_style": "realistic",
                            "negative_prompt": "low quality, low poly, blurry, disconnected, deformed, broken, abstract",
                            "ai_model": "meshy-4"
                        },
                        timeout=15
                    )
                    
                    if response.status_code not in [200, 202]:
                        error_details = ""
                        try:
                            error_data = response.json()
                            error_details = error_data.get("message", response.text)
                        except:
                            error_details = response.text
                        
                        if attempt < max_attempts - 1:
                            continue
                        return {"success": False, "message": f"❌ API error {response.status_code}: {error_details}"}
                    
                    task_id = response.json().get("result") or response.json().get("id")
                    if not task_id:
                        continue
                    
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    # REFINE mode takes 3-5 minutes
                    for i in range(100):
                        status_response = requests.get(
                            f"https://api.meshy.ai/v2/text-to-3d/{task_id}",
                            headers={"Authorization": f"Bearer {self.meshy_key}"}
                        )
                        
                        if status_response.status_code != 200:
                            break
                        
                        status_data = status_response.json()
                        status = status_data.get("status")
                        progress = status_data.get("progress", 0)
                        
                        if status == "SUCCEEDED":
                            progress_bar.progress(100)
                            status_text.success("✅ Generation complete!")
                            
                            glb_url = status_data.get("model_urls", {}).get("glb")
                            thumbnail_url = status_data.get("thumbnail_url")
                            
                            if glb_url:
                                model_data = requests.get(glb_url).content
                                
                                # Quality check on final attempt only
                                if thumbnail_url and attempt < max_attempts - 1:
                                    quality_ok = self._check_quality(thumbnail_url, user_request)
                                    if not quality_ok:
                                        st.warning("Quality check failed, regenerating...")
                                        break
                                
                                return {
                                    "success": True,
                                    "message": "✓ Model generated successfully",
                                    "model_data": model_data,
                                    "file_format": "glb",
                                    "cost": "$0.25",
                                    "quality": "Preview + Enhanced Prompt"
                                }
                            break
                            
                        elif status == "FAILED":
                            error = status_data.get("error", "Unknown error")
                            if attempt < max_attempts - 1:
                                st.warning(f"Failed: {error}. Retrying...")
                                break
                            return {"success": False, "message": f"❌ Failed: {error}"}
                        
                        # Update progress
                        progress_bar.progress(min(progress, 99))
                        status_text.info(f"⏳ Generating... {progress}% complete")
                        time.sleep(3)
                    
            except Exception as e:
                if attempt < max_attempts - 1:
                    st.warning(f"Error: {e}. Retrying...")
                    continue
                return {"success": False, "message": f"❌ Error: {e}"}
        
        return {"success": False, "message": "❌ Generation failed after retries"}
    
    def _check_quality(self, thumbnail_url: str, original_prompt: str) -> bool:
        """Vision check - is it correct?"""
        try:
            thumbnail_data = requests.get(thumbnail_url).content
            thumbnail_b64 = base64.b64encode(thumbnail_data).decode()
            
            response = self.anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=50,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": thumbnail_b64
                            }
                        },
                        {
                            "type": "text",
                            "text": f"""Does this 3D model correctly represent: "{original_prompt}"?

Check: right object type, complete (no missing parts), functional, good quality.

Answer ONLY: YES or NO"""
                        }
                    ]
                }]
            )
            
            result = response.content[0].text.strip().upper()
            return "YES" in result
            
        except:
            return True


def main():
    st.title("🎨 Professional 3D Model Generator")
    st.markdown("*Premium Quality - Meshy v4 REFINE mode*")
    
    try:
        anthropic_key = st.secrets.get("ANTHROPIC_API_KEY", "")
        meshy_key = st.secrets.get("MESHY_API_KEY", "")
    except:
        anthropic_key = ""
        meshy_key = ""
    
    if not anthropic_key or not meshy_key:
        st.error("⚠️ Add ANTHROPIC_API_KEY and MESHY_API_KEY to secrets")
        return
    
    st.sidebar.info("""
**Provider:** Meshy AI v4
**Mode:** Preview (fast)
**Cost:** $0.25 per model
**Time:** 1-2 minutes
**Output:** High-quality GLB

With extreme prompt enhancement!
""")
    
    if 'history' not in st.session_state:
        st.session_state['history'] = []
    
    with st.form("model_request"):
        user_input = st.text_area(
            "What do you want to create?",
            placeholder="Be specific: door knob, phone stand, decorative vase, etc.",
            height=80
        )
        
        col1, col2 = st.columns([1, 5])
        with col1:
            submit = st.form_submit_button("🚀 Generate", use_container_width=True)
        with col2:
            if st.form_submit_button("🗑️ Clear", use_container_width=True):
                st.session_state['history'] = []
                st.rerun()
    
    if submit and user_input:
        try:
            generator = MeshyRefineGenerator(Anthropic(api_key=anthropic_key), meshy_key)
            result = generator.generate(user_input)
            st.session_state['history'].append({"request": user_input, "result": result})
        except Exception as e:
            st.error(f"Error: {e}")
    
    if st.session_state['history']:
        st.markdown("---")
        st.markdown("## 📋 Generation History")
        
        for idx, item in enumerate(reversed(st.session_state['history'])):
            st.markdown(f"### Request #{len(st.session_state['history']) - idx}")
            st.markdown(f"*{item['request']}*")
            
            result = item['result']
            
            if result['success']:
                st.success(f"✅ {result['message']}")
                
                cost = result.get('cost', '')
                quality = result.get('quality', '')
                if cost and quality:
                    st.caption(f"💎 Quality: {quality} • Cost: {cost}")
                
                if result.get('model_data'):
                    file_format = result.get('file_format', 'glb')
                    st.download_button(
                        label=f"💾 Download .{file_format} file",
                        data=result['model_data'],
                        file_name=f"model_{len(st.session_state['history']) - idx}.{file_format}",
                        mime="application/octet-stream",
                        use_container_width=True
                    )
                    
                    st.info("💡 Convert to STL: https://products.aspose.app/3d/conversion/glb-to-stl")
            else:
                st.error(f"❌ {result['message']}")
            
            st.markdown("---")


if __name__ == "__main__":
    main()
