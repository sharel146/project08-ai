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
    
    def search_printables(self, query: str) -> List[Dict]:
        """Search Printables.com by scraping search results"""
        try:
            st.info(f"🔍 Searching Printables.com for: '{query}'")
            
            # Use actual search URL
            search_url = f"https://www.printables.com/search/models?q={query.replace(' ', '+')}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(search_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                # Parse the HTML to extract model info
                import re
                html = response.text
                
                # Extract model cards - look for model links and thumbnails
                # Printables uses data attributes and specific HTML structure
                models = []
                
                # Find all model URLs
                model_urls = re.findall(r'href="(/model/[^"]+)"', html)
                # Find all thumbnail images
                thumbnails = re.findall(r'<img[^>]+src="([^"]+)"[^>]*class="[^"]*ModelCard', html)
                # Find all titles
                titles = re.findall(r'<h2[^>]*class="[^"]*ModelCard__title[^>]*>([^<]+)</h2>', html)
                
                # Combine them
                for i in range(min(5, len(model_urls))):  # Top 5
                    if i < len(titles) and i < len(thumbnails):
                        models.append({
                            'name': titles[i].strip(),
                            'url': f"https://www.printables.com{model_urls[i]}",
                            'thumbnail': thumbnails[i] if thumbnails[i].startswith('http') else f"https://www.printables.com{thumbnails[i]}",
                            'description': '',
                            'download_url': f"https://www.printables.com{model_urls[i]}"
                        })
                
                return models
            
            return []
            
        except Exception as e:
            st.warning(f"Printables search error: {e}")
            return []
    
    def search_thingiverse(self, query: str) -> List[Dict]:
        """Search Thingiverse by scraping"""
        try:
            st.info(f"🔍 Searching Thingiverse for: '{query}'")
            
            search_url = f"https://www.thingiverse.com/search?q={query.replace(' ', '+')}&type=things"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(search_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                import re
                html = response.text
                
                models = []
                
                # Extract thing URLs
                thing_urls = re.findall(r'href="(/thing:\d+)"', html)
                # Extract thumbnails
                thumbnails = re.findall(r'<img[^>]+src="([^"]+)"[^>]*data-thing', html)
                # Extract titles
                titles = re.findall(r'<span class="thing-name">([^<]+)</span>', html)
                
                for i in range(min(5, len(thing_urls))):
                    if i < len(titles):
                        models.append({
                            'name': titles[i].strip() if i < len(titles) else "Model",
                            'url': f"https://www.thingiverse.com{thing_urls[i]}",
                            'thumbnail': thumbnails[i] if i < len(thumbnails) and thumbnails[i].startswith('http') else "https://via.placeholder.com/300x200",
                            'description': '',
                            'download_url': f"https://www.thingiverse.com{thing_urls[i]}"
                        })
                
                return models
            
            return []
            
        except Exception as e:
            st.warning(f"Thingiverse search error: {e}")
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
        
        found_models = []
        
        # Search Printables
        printables_results = searcher.search_printables(user_input)
        found_models.extend(printables_results)
        
        # Search Thingiverse
        thingiverse_results = searcher.search_thingiverse(user_input)
        found_models.extend(thingiverse_results)
        
        if found_models:
            st.success(f"✅ Found {len(found_models)} existing models!")
            
            # Evaluate each one
            for idx, model in enumerate(found_models):
                with st.expander(f"📦 Option {idx + 1}: {model.get('name', 'Unnamed')}", expanded=(idx == 0)):
                    col1, col2 = st.columns([1, 2])
                    
                    with col1:
                        if model.get('thumbnail'):
                            st.image(model['thumbnail'], width=200)
                    
                    with col2:
                        st.markdown(f"**{model.get('name', 'Unnamed')}**")
                        st.caption(model.get('description', '')[:200])
                        
                        # Evaluate if it matches
                        evaluation = searcher.evaluate_model(model, user_input)
                        
                        if evaluation.get("approved"):
                            st.success(f"✅ {evaluation.get('reason')}")
                            
                            # Download and deliver this model
                            if st.button(f"Use This Model", key=f"use_{idx}"):
                                download_url = model.get('download_url') or model.get('files', [{}])[0].get('url')
                                
                                if download_url:
                                    model_data = requests.get(download_url).content
                                    
                                    st.session_state['history'].append({
                                        "request": user_input,
                                        "result": {
                                            "success": True,
                                            "source": "Existing Model",
                                            "model_data": model_data,
                                            "file_format": "stl",
                                            "cost": "FREE",
                                            "model_name": model.get('name')
                                        }
                                    })
                                    st.rerun()
                        else:
                            st.warning(f"⚠️ {evaluation.get('reason')}")
            
            st.markdown("---")
            if st.button("❌ None of these work - Generate New Model"):
                st.markdown("### 🎨 Step 2: Generating New Model")
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
                    st.success(f"✅ Found existing model: {result.get('model_name')} • Cost: FREE!")
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
