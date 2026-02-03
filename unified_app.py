"""
Smart 3D Model System
1. Search existing models online (FREE!)
2. If good one found → deliver it
3. If not found → generate with AI ($0.25)
"""

import streamlit as st
import requests
import time
import base64
from anthropic import Anthropic
from typing import Dict, Optional, List

st.set_page_config(page_title="AI 3D Model Generator", page_icon="🎨", layout="wide")

st.markdown("""
<style>
    .stApp {
        background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
        color: #fff;
    }
</style>
""", unsafe_allow_html=True)


class ModelSearcher:
    def __init__(self, anthropic_client: Anthropic):
        self.client = anthropic_client
    
    def search_models(self, query: str) -> List[Dict]:
        """Search for 3D models using web_fetch to get actual HTML"""
        try:
            st.info(f"🔍 Searching Printables.com for: '{query}'")
            
            # Fetch the actual Printables search page
            search_url = f"https://www.printables.com/search/models?q={query.replace(' ', '%20')}"
            
            # Use web_fetch to get the page
            import subprocess
            import json
            
            # Call web_fetch via the Anthropic client
            search_response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=3000,
                tools=[{
                    "type": "web_fetch_20250513",
                    "name": "web_fetch" 
                }],
                messages=[{
                    "role": "user",
                    "content": f"Fetch this URL and extract 3D model information: {search_url}"
                }]
            )
            
            # Parse response for model data
            models = []
            response_text = ""
            
            for block in search_response.content:
                if hasattr(block, 'text'):
                    response_text += block.text
            
            # Extract model information from response
            import re
            
            # Look for model URLs in the response
            model_urls = re.findall(r'printables\.com/model/(\d+)-([^"\s]+)', response_text)
            
            for idx, (model_id, model_slug) in enumerate(model_urls[:5]):
                model_name = model_slug.replace('-', ' ').replace('_', ' ').title()
                model_url = f"https://www.printables.com/model/{model_id}-{model_slug}"
                
                # Construct thumbnail URL (Printables uses predictable patterns)
                thumbnail_url = f"https://media.printables.com/media/prints/{model_id}/thumbs/cover/640_480_jpg/{model_id}_cover.webp"
                
                models.append({
                    'name': model_name,
                    'url': model_url,
                    'thumbnail': thumbnail_url,
                    'description': '',
                    'download_url': model_url
                })
            
            if not models:
                st.warning("Could not parse models from search results")
            
            return models
            
        except Exception as e:
            st.error(f"Search error: {e}")
            return []
    
    def search_printables(self, query: str) -> List[Dict]:
        """Deprecated - use search_models instead"""
        return []
    
    def search_thingiverse(self, query: str) -> List[Dict]:
        """Deprecated - use search_models instead"""
        return []
    
    def evaluate_model(self, model_info: Dict, user_query: str) -> Dict:
        """Use Claude to check if found model matches what user wants"""
        try:
            model_name = model_info.get("name", "")
            model_desc = model_info.get("description", "")
            model_image = model_info.get("thumbnail", "")
            
            # If there's an image, use vision to check
            if model_image:
                img_data = requests.get(model_image).content
                img_b64 = base64.b64encode(img_data).decode()
                
                response = self.client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=200,
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": img_b64
                                }
                            },
                            {
                                "type": "text",
                                "text": f"""User wants: "{user_query}"

This model is titled: "{model_name}"
Description: "{model_desc}"

Does this 3D model match what the user wants?

APPROVE if:
✅ Correct object type
✅ Good quality visible
✅ Functional design
✅ Printable

REJECT if:
❌ Wrong object
❌ Low quality/broken
❌ Too complex/decorative when functional needed
❌ Doesn't match request

Respond JSON:
{{"approved": true/false, "reason": "brief explanation", "confidence": "high/medium/low"}}"""
                            }
                        ]
                    }]
                )
                
                result_text = response.content[0].text.strip()
                import re, json
                json_match = re.search(r'\{[^}]+\}', result_text)
                if json_match:
                    return json.loads(json_match.group())
            
            return {"approved": False, "reason": "No image to evaluate", "confidence": "low"}
            
        except:
            return {"approved": False, "reason": "Evaluation failed", "confidence": "low"}


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
            with st.spinner("🎨 Generating new model with AI..."):
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
                                    "source": "AI Generated",
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
2. ✅ If good match → deliver it
3. 🎨 If not found → generate ($0.25)

Saves money, faster results!
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
        searcher = ModelSearcher(Anthropic(api_key=anthropic_key))
        generator = MeshyGenerator(meshy_key, Anthropic(api_key=anthropic_key))
        
        # Step 1: Search existing models
        st.markdown("### 🔍 Step 1: Searching Existing Models")
        
        found_models = searcher.search_models(user_input)
        
        if found_models:
            st.success(f"✅ Found {len(found_models)} existing models!")
            
            # Show each model with thumbnail
            for idx, model in enumerate(found_models):
                with st.expander(f"📦 Option {idx + 1}: {model.get('name', 'Unnamed')}", expanded=(idx == 0)):
                    col1, col2 = st.columns([1, 2])
                    
                    with col1:
                        # Show thumbnail
                        thumbnail = model.get('thumbnail')
                        if thumbnail:
                            try:
                                st.image(thumbnail, width=250, caption="Preview")
                            except:
                                st.warning("⚠️ Image failed to load")
                    
                    with col2:
                        st.markdown(f"### {model.get('name', 'Unnamed')}")
                        st.markdown(f"🔗 [View full model page]({model.get('url')})")
                        
                        col_a, col_b = st.columns(2)
                        
                        with col_a:
                            if st.button(f"✅ Use This (FREE)", key=f"use_{idx}", use_container_width=True):
                                st.session_state['history'].append({
                                    "request": user_input,
                                    "result": {
                                        "success": True,
                                        "source": "Existing Model",
                                        "model_data": None,
                                        "model_url": model.get('url'),
                                        "thumbnail": model.get('thumbnail'),
                                        "file_format": "stl",
                                        "cost": "FREE",
                                        "model_name": model.get('name')
                                    }
                                })
                                st.rerun()
                        
                        with col_b:
                            st.link_button("🌐 Open Page", model.get('url'), use_container_width=True)
            
            st.markdown("---")
            if st.button("❌ None of these work - Generate New Model ($0.25)", use_container_width=True):
                st.markdown("### 🎨 Generating New Model")
                result = generator.generate(user_input)
                st.session_state['history'].append({"request": user_input, "result": result})
                st.rerun()
        
        else:
            st.warning("❌ No existing models found")
            st.markdown("### 🎨 Generating New Model")
            result = generator.generate(user_input)
            st.session_state['history'].append({"request": user_input, "result": result})
            st.rerun()
    
    # History
    if st.session_state['history']:
        st.markdown("---")
        st.markdown("## 📋 Your Models")
        
        for idx, item in enumerate(reversed(st.session_state['history'])):
            st.markdown(f"### Model #{len(st.session_state['history']) - idx}")
            st.markdown(f"*{item['request']}*")
            
            result = item['result']
            
            if result['success']:
                source = result.get('source', 'Unknown')
                cost = result.get('cost', '')
                
                if source == "Existing Model":
                    st.success(f"✅ Using existing model: {result.get('model_name')} • Cost: FREE!")
                    
                    # Show thumbnail if available
                    thumbnail = result.get('thumbnail')
                    if thumbnail:
                        try:
                            st.image(thumbnail, width=300)
                        except:
                            pass
                    
                    model_url = result.get('model_url')
                    if model_url:
                        st.link_button("🌐 Download from source", model_url, use_container_width=True)
                        st.info("💡 Click above to download the STL file from Printables/Thingiverse")
                else:
                    st.success(f"✅ Generated new model • Cost: {cost}")
                
                if result.get('model_data'):
                    file_ext = result.get('file_format', 'glb')
                    st.download_button(
                        label=f"💾 Download .{file_ext}",
                        data=result['model_data'],
                        file_name=f"model_{len(st.session_state['history']) - idx}.{file_ext}",
                        mime="application/octet-stream",
                        use_container_width=True
                    )
            else:
                st.error(f"❌ {result.get('message')}")
            
            st.markdown("---")


if __name__ == "__main__":
    main()
