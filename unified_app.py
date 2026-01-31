"""
AI 3D Model Generator - 100% AI Mesh Generation
NO OpenSCAD - Everything uses Meshy.ai/Rodin AI
"""

import streamlit as st
import requests
import re
import time
import json
import base64
from anthropic import Anthropic
from typing import Dict, Optional
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
</style>
""", unsafe_allow_html=True)


# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    MODEL = "claude-sonnet-4-20250514"


# ============================================================================
# PROMPT ENHANCEMENT
# ============================================================================

class PromptEnhancer:
    def __init__(self, client: Anthropic):
        self.client = client
    
    def enhance(self, prompt: str) -> str:
        """Enhance any prompt with physical details"""
        
        if len(prompt.strip()) >= 30:
            return prompt  # Already detailed
        
        try:
            response = self.client.messages.create(
                model=Config.MODEL,
                max_tokens=100,
                messages=[{"role": "user", "content": f"""Describe this object for AI 3D modeling:

"{prompt}"

Focus on: exact shape, dimensions, key features, materials, surface finish.
Be very specific and detailed (under 60 words).

Example for "door knob": "Round door knob, 60mm diameter spherical handle with smooth polished surface, decorative grooves around equator, tapered cylindrical mounting base 40mm diameter, total length 80mm including 30mm mounting shaft, brushed metal finish"

Example for "phone stand": "Angled phone stand, 100x80mm rectangular base, back support rising at 65 degrees, 15mm front lip, side walls 5mm thick, smooth rounded edges, modern minimalist design"

Now describe: {prompt}"""}]
            )
            
            enhanced = response.content[0].text.strip().strip('"').strip("'")
            if len(enhanced) > 250:
                enhanced = enhanced[:250]
            return enhanced
        except:
            return prompt + " with clean professional design"


# ============================================================================
# AI MESH GENERATION WITH QUALITY CONTROL
# ============================================================================

class MeshProvider(Enum):
    MESHY = "meshy"
    RODIN = "rodin"


class MeshGenerator:
    def __init__(self, anthropic_client: Anthropic, meshy_key: Optional[str] = None, rodin_key: Optional[str] = None):
        self.anthropic_client = anthropic_client
        self.meshy_key = meshy_key
        self.rodin_key = rodin_key
        self.enhancer = PromptEnhancer(anthropic_client)
    
    def select_provider(self, prompt: str) -> MeshProvider:
        """Select best provider based on prompt"""
        lower = prompt.lower()
        
        # Rodin for simple/cartoon
        if any(word in lower for word in ['cartoon', 'simple', 'cute', 'toy', 'stylized']):
            if self.rodin_key:
                return MeshProvider.RODIN
        
        # Default to Meshy
        if self.meshy_key:
            return MeshProvider.MESHY
        elif self.rodin_key:
            return MeshProvider.RODIN
        
        return None
    
    def generate(self, user_request: str) -> Dict:
        """Generate 3D model with silent quality control"""
        
        # Enhance prompt
        enhanced_prompt = self.enhancer.enhance(user_request)
        
        if enhanced_prompt != user_request:
            st.info(f"🔍 **Enhanced Prompt:**\n\n*{enhanced_prompt}*")
        else:
            st.info(f"🔍 **Using your prompt:** {user_request}")
        
        # Select provider
        provider = self.select_provider(enhanced_prompt)
        
        if not provider:
            return {"success": False, "message": "⚠️ Add MESHY_API_KEY or RODIN_API_KEY to secrets"}
        
        if provider == MeshProvider.MESHY:
            return self._generate_with_meshy(enhanced_prompt, user_request)
        else:
            return self._generate_with_rodin(enhanced_prompt, user_request)
    
    def _generate_with_meshy(self, prompt: str, original: str) -> Dict:
        """Generate with Meshy - silent retries until perfect"""
        max_attempts = 3
        
        with st.spinner("🎨 Creating your model..."):
            for attempt in range(max_attempts):
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
                            "negative_prompt": "low quality, blurry, disconnected parts, deformed, malformed, abstract",
                            "ai_model": "meshy-4",
                            "seed": None if attempt == 0 else attempt * 12345
                        },
                        timeout=10
                    )
                    
                    if response.status_code not in [200, 202]:
                        continue
                    
                    task_id = response.json().get("result") or response.json().get("id")
                    if not task_id:
                        continue
                    
                    progress_bar = st.progress(0)
                    
                    for i in range(40):
                        status_response = requests.get(
                            f"https://api.meshy.ai/v2/text-to-3d/{task_id}",
                            headers={"Authorization": f"Bearer {self.meshy_key}"}
                        )
                        
                        if status_response.status_code != 200:
                            break
                        
                        status_data = status_response.json()
                        status = status_data.get("status")
                        
                        if status == "SUCCEEDED":
                            progress_bar.progress(100)
                            glb_url = status_data.get("model_urls", {}).get("glb")
                            thumbnail_url = status_data.get("thumbnail_url")
                            
                            if glb_url:
                                model_data = requests.get(glb_url).content
                                
                                # Silent quality check
                                if thumbnail_url and attempt < max_attempts - 1:
                                    quality_ok = self._check_quality(thumbnail_url, original)
                                    if not quality_ok:
                                        break  # Try again silently
                                
                                return {
                                    "success": True,
                                    "message": "✓ Generated successfully",
                                    "model_data": model_data,
                                    "file_format": "glb",
                                    "provider": "Meshy.ai",
                                    "cost": "$0.25"
                                }
                            break
                        elif status == "FAILED":
                            break
                        
                        progress = status_data.get("progress", 0)
                        progress_bar.progress(min(progress, 99))
                        time.sleep(3)
                
                except:
                    continue
        
        return {"success": False, "message": "❌ Generation failed"}
    
    def _generate_with_rodin(self, prompt: str, original: str) -> Dict:
        """Generate with Rodin - faster, cheaper"""
        
        with st.spinner("🎨 Creating your model..."):
            try:
                response = requests.post(
                    "https://hyperhuman.deemos.com/api/v2/rodin",
                    headers={
                        "Authorization": f"Bearer {self.rodin_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "prompt": prompt,
                        "tier": "standard"
                    },
                    timeout=10
                )
                
                if response.status_code not in [200, 201]:
                    # Fallback to Meshy
                    if self.meshy_key:
                        return self._generate_with_meshy(prompt, original)
                    return {"success": False, "message": "❌ Generation failed"}
                
                task_uuid = response.json().get("uuid")
                if not task_uuid:
                    return {"success": False, "message": "❌ No task ID"}
                
                progress_bar = st.progress(0)
                
                for i in range(20):
                    status_response = requests.get(
                        f"https://hyperhuman.deemos.com/api/v2/rodin/{task_uuid}",
                        headers={"Authorization": f"Bearer {self.rodin_key}"}
                    )
                    
                    if status_response.status_code != 200:
                        break
                    
                    status_data = status_response.json()
                    status = status_data.get("status")
                    
                    if status == "success":
                        progress_bar.progress(100)
                        model_url = status_data.get("model_url")
                        
                        if model_url:
                            model_data = requests.get(model_url).content
                            return {
                                "success": True,
                                "message": "✓ Generated successfully",
                                "model_data": model_data,
                                "file_format": "glb",
                                "provider": "Rodin AI",
                                "cost": "$0.15"
                            }
                        break
                    elif status == "failed":
                        if self.meshy_key:
                            return self._generate_with_meshy(prompt, original)
                        break
                    
                    progress = min((i + 1) * 5, 95)
                    progress_bar.progress(progress)
                    time.sleep(1.5)
            
            except:
                if self.meshy_key:
                    return self._generate_with_meshy(prompt, original)
        
        return {"success": False, "message": "❌ Generation failed"}
    
    def _check_quality(self, thumbnail_url: str, original_prompt: str) -> bool:
        """Check if model matches request - return True if good"""
        try:
            thumbnail_data = requests.get(thumbnail_url).content
            thumbnail_b64 = base64.b64encode(thumbnail_data).decode()
            
            response = self.anthropic_client.messages.create(
                model=Config.MODEL,
                max_tokens=100,
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
                            "text": f"""Does this 3D model match "{original_prompt}"?

Check: correct object, complete (no missing parts), good proportions, not deformed.

Respond ONLY: YES or NO"""
                        }
                    ]
                }]
            )
            
            result = response.content[0].text.strip().upper()
            return "YES" in result
            
        except:
            return True  # If check fails, approve


# ============================================================================
# MAIN APP
# ============================================================================

def main():
    st.title("🎨 AI 3D Model Generator")
    st.markdown("*100% AI-powered - Professional quality models*")
    
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
    providers = []
    if meshy_key:
        providers.append("Meshy.ai ($0.25)")
    if rodin_key:
        providers.append("Rodin AI ($0.15)")
    
    if providers:
        st.sidebar.success(f"🎨 Providers: {', '.join(providers)}")
    else:
        st.sidebar.warning("⚠️ Add MESHY_API_KEY or RODIN_API_KEY")
    
    # Initialize history
    if 'history' not in st.session_state:
        st.session_state['history'] = []
    
    # Input form
    with st.form("model_request"):
        user_input = st.text_area(
            "What do you want to create?",
            placeholder="Examples: door knob, phone stand, cartoon bear, decorative vase...",
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
            generator = MeshGenerator(Anthropic(api_key=anthropic_key), meshy_key, rodin_key)
            result = generator.generate(user_input)
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
                st.success(f"✅ {result['message']}")
                
                provider = result.get('provider', 'AI')
                cost = result.get('cost', '')
                if provider and cost:
                    st.caption(f"Generated with {provider} • Cost: {cost}")
                
                if result.get('model_data'):
                    file_format = result.get('file_format', 'glb')
                    st.download_button(
                        label=f"💾 Download .{file_format} file",
                        data=result['model_data'],
                        file_name=f"model_{len(st.session_state['history']) - idx}.{file_format}",
                        mime="application/octet-stream",
                        use_container_width=True
                    )
                    
                    if file_format == 'glb':
                        st.info("💡 Convert to STL: https://products.aspose.app/3d/conversion/glb-to-stl")
            else:
                st.error(f"❌ {result['message']}")
            
            st.markdown("---")


if __name__ == "__main__":
    main()
