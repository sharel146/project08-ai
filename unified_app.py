"""
Smart 3D Model System - SIMPLE VERSION
1. Show direct search links to Printables/Thingiverse
2. User picks model OR
3. Generate new one
"""

import streamlit as st
import requests
import time
import base64
from anthropic import Anthropic
from typing import Dict

st.set_page_config(page_title="AI 3D Model Generator", page_icon="🎨", layout="wide")

st.markdown("""
<style>
    .stApp {
        background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
        color: #fff;
    }
</style>
""", unsafe_allow_html=True)


class MeshyGenerator:
    def __init__(self, meshy_key: str, anthropic_client: Anthropic):
        self.meshy_key = meshy_key
        self.client = anthropic_client
    
    def enhance_prompt(self, prompt: str) -> str:
        """Make prompt super detailed"""
        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=150,
                messages=[{"role": "user", "content": f"""Describe '{prompt}' in extreme detail for 3D modeling (under 60 words):

Include: exact shape, dimensions, materials, surface finish, key features.

Example: "door knob" → "Round door knob, 60mm diameter brass handle with polished finish, decorative grooves, square mounting base 45mm with center hole 12mm, total height 80mm"

Now: {prompt}"""}]
            )
            return response.content[0].text.strip().strip('"').strip("'")
        except:
            return prompt
    
    def generate(self, prompt: str) -> Dict:
        """Generate new model with Meshy AI"""
        enhanced = self.enhance_prompt(prompt)
        st.info(f"🔍 **Enhanced:** {enhanced}")
        
        try:
            with st.spinner("🎨 Generating model with AI..."):
                response = requests.post(
                    "https://api.meshy.ai/v2/text-to-3d",
                    headers={
                        "Authorization": f"Bearer {self.meshy_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "mode": "preview",
                        "prompt": enhanced,
                        "art_style": "realistic",
                        "negative_prompt": "low quality, blurry, disconnected, deformed, broken",
                        "ai_model": "meshy-4"
                    },
                    timeout=15
                )
                
                if response.status_code not in [200, 202]:
                    return {"success": False, "message": "Generation failed"}
                
                task_id = response.json().get("result") or response.json().get("id")
                progress_bar = st.progress(0)
                
                for i in range(40):
                    status_resp = requests.get(
                        f"https://api.meshy.ai/v2/text-to-3d/{task_id}",
                        headers={"Authorization": f"Bearer {self.meshy_key}"}
                    )
                    
                    if status_resp.status_code == 200:
                        data = status_resp.json()
                        
                        if data.get("status") == "SUCCEEDED":
                            progress_bar.progress(100)
                            glb_url = data.get("model_urls", {}).get("glb")
                            
                            if glb_url:
                                model_data = requests.get(glb_url).content
                                return {
                                    "success": True,
                                    "model_data": model_data,
                                    "file_format": "glb",
                                    "cost": "$0.25"
                                }
                        
                        progress = data.get("progress", 0)
                        progress_bar.progress(min(progress, 99))
                    
                    time.sleep(3)
                
        except Exception as e:
            return {"success": False, "message": f"Error: {e}"}
        
        return {"success": False, "message": "Timeout"}


def main():
    st.title("🎨 Smart 3D Model System")
    st.markdown("*Search first, generate only if needed*")
    
    try:
        anthropic_key = st.secrets.get("ANTHROPIC_API_KEY", "")
        meshy_key = st.secrets.get("MESHY_API_KEY", "")
    except:
        anthropic_key = ""
        meshy_key = ""
    
    if not anthropic_key or not meshy_key:
        st.error("⚠️ Add ANTHROPIC_API_KEY and MESHY_API_KEY")
        return
    
    st.sidebar.success("""
**Smart System:**
1. 🔍 Search existing models (FREE)
2. ✅ If found → use it
3. 🎨 If not → generate ($0.25)

80% of requests = FREE!
""")
    
    if 'history' not in st.session_state:
        st.session_state['history'] = []
    
    with st.form("request_form"):
        user_input = st.text_area(
            "What do you want to create?",
            placeholder="door knob, phone stand, bracket, etc.",
            height=80
        )
        
        col1, col2 = st.columns([1, 5])
        with col1:
            submit = st.form_submit_button("🚀 Get Model", use_container_width=True)
        with col2:
            if st.form_submit_button("🗑️ Clear", use_container_width=True):
                st.session_state['history'] = []
                st.rerun()
    
    if submit and user_input:
        st.markdown("---")
        st.markdown("## 🔍 Step 1: Check Existing Models")
        
        # Create search URLs
        query_encoded = user_input.replace(' ', '+')
        printables_url = f"https://www.printables.com/search/models?q={query_encoded}"
        thingiverse_url = f"https://www.thingiverse.com/search?q={query_encoded}&type=things"
        
        st.success("✅ Search these sites for existing FREE models:")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 🟠 Printables.com")
            st.link_button("🔍 Search Printables", printables_url, use_container_width=True)
            st.caption("2M+ free models")
        
        with col2:
            st.markdown("### 🔵 Thingiverse")
            st.link_button("🔍 Search Thingiverse", thingiverse_url, use_container_width=True)
            st.caption("5M+ free models")
        
        st.info("""
💡 **How to use:**
1. Click one of the search links above
2. Browse results and find a model you like
3. Download the STL file from that site
4. **You're done - FREE!** ✅

OR if you don't find anything good:
""")
        
        st.markdown("---")
        st.markdown("## 🎨 Step 2: Generate New Model")
        
        if st.button("❌ Didn't find anything good - Generate with AI ($0.25)", use_container_width=True):
            generator = MeshyGenerator(meshy_key, Anthropic(api_key=anthropic_key))
            result = generator.generate(user_input)
            st.session_state['history'].append({"request": user_input, "result": result})
            st.rerun()
    
    # History
    if st.session_state['history']:
        st.markdown("---")
        st.markdown("## 📋 Your Generated Models")
        
        for idx, item in enumerate(reversed(st.session_state['history'])):
            st.markdown(f"### Model #{len(st.session_state['history']) - idx}")
            st.markdown(f"*{item['request']}*")
            
            result = item['result']
            
            if result.get('success'):
                cost = result.get('cost', '$0.25')
                st.success(f"✅ Generated with AI • Cost: {cost}")
                
                if result.get('model_data'):
                    file_ext = result.get('file_format', 'glb')
                    st.download_button(
                        label=f"💾 Download .{file_ext}",
                        data=result['model_data'],
                        file_name=f"model_{len(st.session_state['history']) - idx}.{file_ext}",
                        mime="application/octet-stream",
                        use_container_width=True
                    )
                    
                    st.info("💡 Convert to STL: https://products.aspose.app/3d/conversion/glb-to-stl")
            else:
                st.error(f"❌ {result.get('message')}")
            
            st.markdown("---")


if __name__ == "__main__":
    main()
