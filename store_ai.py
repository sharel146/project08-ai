"""
Autonomous 3D Modeling Agent
Generates OpenSCAD code from natural language, with self-correction and smart classification.
Optimized for Bambu Lab A1 printer.
"""

import os
import subprocess
import re
from anthropic import Anthropic
from typing import Dict, List, Optional, Tuple
from enum import Enum
import json

# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Configuration settings for the agent"""
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    MODEL = "claude-sonnet-4-20250514"
    MAX_CORRECTION_ATTEMPTS = 5
    OPENSCAD_TIMEOUT = 30  # seconds
    OPENSCAD_BINARY = "openscad"  # Update path if needed
    
    # Bambu Lab A1 build volume (mm)
    BUILD_VOLUME = {
        "x": 256,
        "y": 256, 
        "z": 256
    }


class RequestType(Enum):
    """Classification of user requests"""
    FUNCTIONAL = "functional"  # Geometric, mathematical parts
    ORGANIC = "organic"        # Curved, artistic, sculptural
    UNKNOWN = "unknown"


# ============================================================================
# ERROR CATEGORIZATION
# ============================================================================

class ErrorCategory(Enum):
    """Types of OpenSCAD errors we can intelligently handle"""
    SYNTAX = "syntax"                    # Missing semicolons, brackets, etc.
    UNDEFINED_VARIABLE = "undefined"     # Using variables before definition
    INVALID_OPERATION = "invalid_op"     # Mathematical errors
    GEOMETRY_ERROR = "geometry"          # Invalid shapes or transformations
    COMPILATION_FAILED = "compilation"   # General compilation failure
    UNKNOWN = "unknown"


def categorize_error(error_message: str) -> Tuple[ErrorCategory, str]:
    """
    Analyze OpenSCAD error message and categorize it.
    Returns: (category, relevant_excerpt)
    """
    error_lower = error_message.lower()
    
    # Syntax errors
    if any(keyword in error_lower for keyword in ["syntax error", "parse error", "expected ';'"]):
        return ErrorCategory.SYNTAX, error_message
    
    # Undefined variables
    if "not defined" in error_lower or "unknown variable" in error_lower:
        match = re.search(r"'([^']+)' .*not defined", error_message)
        var_name = match.group(1) if match else "unknown"
        return ErrorCategory.UNDEFINED_VARIABLE, f"Variable '{var_name}' not defined"
    
    # Invalid operations
    if "division by zero" in error_lower or "invalid value" in error_lower:
        return ErrorCategory.INVALID_OPERATION, error_message
    
    # Geometry errors
    if any(keyword in error_lower for keyword in ["geometry", "manifold", "invalid shape"]):
        return ErrorCategory.GEOMETRY_ERROR, error_message
    
    # Compilation failed
    if "compilation failed" in error_lower:
        return ErrorCategory.COMPILATION_FAILED, error_message
    
    return ErrorCategory.UNKNOWN, error_message


# ============================================================================
# MANUAL FALLBACK PATTERNS
# ============================================================================

class FallbackPatterns:
    """Pre-defined OpenSCAD templates for common, reliable patterns"""
    
    @staticmethod
    def funnel(top_diameter: float = 100, bottom_diameter: float = 20, 
               height: float = 80, wall_thickness: float = 2) -> str:
        """Generate a reliable funnel design"""
        return f"""
// Parametric Funnel - Tested & Reliable
top_d = {top_diameter};
bottom_d = {bottom_diameter};
height = {height};
wall = {wall_thickness};

difference() {{
    // Outer cone
    cylinder(h=height, r1=top_d/2, r2=bottom_d/2, $fn=100);
    
    // Inner cone (hollowed out)
    translate([0, 0, wall])
        cylinder(h=height, r1=(top_d/2)-wall, r2=(bottom_d/2)-wall, $fn=100);
}}

// Spout extension
translate([0, 0, -10])
    cylinder(h=10, r=bottom_d/2, $fn=50);
"""
    
    @staticmethod
    def bracket(width: float = 50, height: float = 40, 
                thickness: float = 5, hole_diameter: float = 5) -> str:
        """Generate an L-bracket with mounting holes"""
        return f"""
// L-Bracket with Mounting Holes
width = {width};
height = {height};
thick = {thickness};
hole_d = {hole_diameter};

difference() {{
    union() {{
        // Vertical part
        cube([thick, width, height]);
        
        // Horizontal part
        cube([width, width, thick]);
    }}
    
    // Mounting holes in vertical part
    translate([thick/2, width/2, height - 10])
        rotate([0, 90, 0])
        cylinder(h=thick*2, r=hole_d/2, center=true, $fn=30);
    
    // Mounting holes in horizontal part
    translate([width - 10, width/2, thick/2])
        cylinder(h=thick*2, r=hole_d/2, center=true, $fn=30);
}}
"""
    
    @staticmethod
    def box(length: float = 100, width: float = 80, height: float = 60,
            wall_thickness: float = 2, lid: bool = False) -> str:
        """Generate a parametric box with optional lid"""
        lid_code = ""
        if lid:
            lid_code = f"""
// Lid (print separately)
translate([0, {width + 10}, 0])
difference() {{
    cube([{length}, {width}, 5]);
    translate([{wall_thickness}, {wall_thickness}, -1])
        cube([{length - 2*wall_thickness}, {width - 2*wall_thickness}, 7]);
}}
"""
        
        return f"""
// Parametric Box
length = {length};
width = {width};
height = {height};
wall = {wall_thickness};

// Main box
difference() {{
    cube([length, width, height]);
    translate([wall, wall, wall])
        cube([length - 2*wall, width - 2*wall, height]);
}}

{lid_code}
"""


# ============================================================================
# REQUEST CLASSIFIER
# ============================================================================

class RequestClassifier:
    """Uses Claude to classify whether a request is functional or organic"""
    
    def __init__(self, client: Anthropic):
        self.client = client
    
    def classify(self, user_request: str) -> RequestType:
        """
        Classify the user's request as functional or organic.
        Returns RequestType enum.
        """
        
        classification_prompt = f"""You are a 3D modeling expert. Classify this request:

USER REQUEST: "{user_request}"

Classify as either:
- FUNCTIONAL: Geometric, mechanical, mathematical parts (brackets, gears, funnels, boxes, connectors, mounts, etc.)
- ORGANIC: Curved, artistic, sculptural, nature-inspired shapes (figurines, statues, animals, faces, etc.)

Functional parts work well with OpenSCAD (programmatic/parametric modeling).
Organic parts need mesh-based modeling and are NOT suitable for OpenSCAD.

Respond with ONLY one word: FUNCTIONAL or ORGANIC"""

        try:
            response = self.client.messages.create(
                model=Config.MODEL,
                max_tokens=10,
                messages=[{"role": "user", "content": classification_prompt}]
            )
            
            classification = response.content[0].text.strip().upper()
            
            if "FUNCTIONAL" in classification:
                return RequestType.FUNCTIONAL
            elif "ORGANIC" in classification:
                return RequestType.ORGANIC
            else:
                return RequestType.UNKNOWN
                
        except Exception as e:
            print(f"Classification error: {e}")
            return RequestType.UNKNOWN


# ============================================================================
# OPENSCAD COMPILER
# ============================================================================

class OpenSCADCompiler:
    """Handles compilation and validation of OpenSCAD code"""
    
    @staticmethod
    def compile(code: str, output_path: str = "/tmp/test_model.stl") -> Tuple[bool, str]:
        """
        Compile OpenSCAD code to STL.
        Returns: (success: bool, error_message: str)
        """
        
        # Write code to temporary file
        temp_scad = "/tmp/temp_model.scad"
        try:
            with open(temp_scad, 'w') as f:
                f.write(code)
        except Exception as e:
            return False, f"Failed to write temporary file: {e}"
        
        # Attempt compilation
        try:
            result = subprocess.run(
                [Config.OPENSCAD_BINARY, "-o", output_path, temp_scad],
                capture_output=True,
                text=True,
                timeout=Config.OPENSCAD_TIMEOUT
            )
            
            if result.returncode == 0:
                return True, "Compilation successful"
            else:
                error_msg = result.stderr if result.stderr else result.stdout
                return False, error_msg
                
        except subprocess.TimeoutExpired:
            return False, "Compilation timeout - model may be too complex"
        except FileNotFoundError:
            return False, f"OpenSCAD not found at '{Config.OPENSCAD_BINARY}'. Please install OpenSCAD."
        except Exception as e:
            return False, f"Compilation error: {e}"


# ============================================================================
# CODE GENERATOR WITH SELF-CORRECTION
# ============================================================================

class ModelGenerator:
    """Generates OpenSCAD code with self-correction loop"""
    
    def __init__(self, client: Anthropic):
        self.client = client
        self.compiler = OpenSCADCompiler()
    
    def generate(self, user_request: str, attempt: int = 1) -> Tuple[bool, str, str]:
        """
        Generate OpenSCAD code from natural language.
        Returns: (success, scad_code, message)
        """
        
        if attempt > Config.MAX_CORRECTION_ATTEMPTS:
            return False, "", f"Failed after {Config.MAX_CORRECTION_ATTEMPTS} attempts"
        
        # Build the prompt
        system_prompt = f"""You are an expert OpenSCAD programmer specializing in 3D printable models for Bambu Lab A1 printer.

BUILD VOLUME: {Config.BUILD_VOLUME['x']}mm x {Config.BUILD_VOLUME['y']}mm x {Config.BUILD_VOLUME['z']}mm

CRITICAL RULES:
1. Generate ONLY valid OpenSCAD code - no explanations, no markdown
2. Use $fn for smooth curves (minimum $fn=50 for visible surfaces)
3. All dimensions in millimeters
4. Ensure wall thickness >= 1.2mm for printability
5. Add support structures if overhangs exceed 45°
6. Keep models within build volume
7. Use descriptive variable names and comments

RESPOND WITH OPENSCAD CODE ONLY."""

        messages = [{"role": "user", "content": f"Create this 3D model:\n\n{user_request}"}]
        
        try:
            response = self.client.messages.create(
                model=Config.MODEL,
                max_tokens=4000,
                system=system_prompt,
                messages=messages
            )
            
            scad_code = self._extract_code(response.content[0].text)
            
            # Test compilation
            success, error_msg = self.compiler.compile(scad_code)
            
            if success:
                return True, scad_code, "✓ Model generated successfully"
            else:
                # Categorize the error
                error_category, error_excerpt = categorize_error(error_msg)
                print(f"\n⚠ Attempt {attempt}: {error_category.value} error")
                print(f"   Error: {error_excerpt[:200]}...")
                
                # Self-correct
                return self._self_correct(user_request, scad_code, error_msg, 
                                         error_category, attempt)
                
        except Exception as e:
            return False, "", f"Generation error: {e}"
    
    def _extract_code(self, text: str) -> str:
        """Extract OpenSCAD code from response (handles markdown fences)"""
        # Remove markdown code fences if present
        code = re.sub(r'```(?:openscad)?\n', '', text)
        code = re.sub(r'```\s*$', '', code)
        return code.strip()
    
    def _self_correct(self, user_request: str, failed_code: str, 
                     error_msg: str, error_category: ErrorCategory,
                     attempt: int) -> Tuple[bool, str, str]:
        """
        Attempt to fix the failed code based on error category.
        """
        
        correction_prompt = f"""The OpenSCAD code you generated has a {error_category.value} error.

ORIGINAL REQUEST: {user_request}

FAILED CODE:
{failed_code}

ERROR MESSAGE:
{error_msg}

Fix the error and provide corrected OpenSCAD code. Respond with ONLY the corrected code, no explanations."""

        try:
            response = self.client.messages.create(
                model=Config.MODEL,
                max_tokens=4000,
                messages=[{"role": "user", "content": correction_prompt}]
            )
            
            corrected_code = self._extract_code(response.content[0].text)
            
            # Test the correction
            success, new_error = self.compiler.compile(corrected_code)
            
            if success:
                return True, corrected_code, f"✓ Fixed after {attempt} attempt(s)"
            else:
                # Recurse for another attempt
                return self.generate(user_request, attempt + 1)
                
        except Exception as e:
            return False, "", f"Correction error: {e}"


# ============================================================================
# MAIN AGENT
# ============================================================================

class ModelAgent:
    """Main autonomous 3D modeling agent"""
    
    def __init__(self, api_key: str):
        self.client = Anthropic(api_key=api_key)
        self.classifier = RequestClassifier(self.client)
        self.generator = ModelGenerator(self.client)
        self.fallbacks = FallbackPatterns()
    
    def process_request(self, user_input: str) -> Dict:
        """
        Main entry point - processes user request and returns result.
        
        Returns dict with:
            - success: bool
            - request_type: str
            - scad_code: str
            - message: str
            - fallback_used: bool
        """
        
        print(f"\n{'='*60}")
        print(f"REQUEST: {user_input}")
        print(f"{'='*60}")
        
        # Step 1: Classify request
        request_type = self.classifier.classify(user_input)
        print(f"Classification: {request_type.value.upper()}")
        
        # Step 2: Handle organic requests
        if request_type == RequestType.ORGANIC:
            return {
                "success": False,
                "request_type": "organic",
                "scad_code": "",
                "message": "⚠ This appears to be an organic/sculptural shape. OpenSCAD is not suitable for organic modeling. Consider using Blender, ZBrush, or AI mesh generators instead.",
                "fallback_used": False
            }
        
        # Step 3: Check for known fallback patterns
        fallback_result = self._check_fallbacks(user_input)
        if fallback_result:
            return fallback_result
        
        # Step 4: Generate with AI
        success, scad_code, message = self.generator.generate(user_input)
        
        return {
            "success": success,
            "request_type": request_type.value,
            "scad_code": scad_code,
            "message": message,
            "fallback_used": False
        }
    
    def _check_fallbacks(self, user_input: str) -> Optional[Dict]:
        """Check if request matches a known fallback pattern"""
        
        user_lower = user_input.lower()
        
        # Funnel detection
        if "funnel" in user_lower:
            print("⚡ Using FALLBACK: Funnel template")
            return {
                "success": True,
                "request_type": "functional",
                "scad_code": self.fallbacks.funnel(),
                "message": "✓ Generated using reliable funnel template",
                "fallback_used": True
            }
        
        # Bracket detection
        if "bracket" in user_lower and "l-bracket" in user_lower or "mounting" in user_lower:
            print("⚡ Using FALLBACK: Bracket template")
            return {
                "success": True,
                "request_type": "functional",
                "scad_code": self.fallbacks.bracket(),
                "message": "✓ Generated using reliable bracket template",
                "fallback_used": True
            }
        
        # Box detection
        if any(word in user_lower for word in ["box", "container", "case"]):
            has_lid = "lid" in user_lower or "cover" in user_lower
            print(f"⚡ Using FALLBACK: Box template (lid={has_lid})")
            return {
                "success": True,
                "request_type": "functional",
                "scad_code": self.fallbacks.box(lid=has_lid),
                "message": "✓ Generated using reliable box template",
                "fallback_used": True
            }
        
        return None
    
    def save_model(self, scad_code: str, filename: str = "model.scad"):
        """Save the generated OpenSCAD code to file"""
        try:
            with open(filename, 'w') as f:
                f.write(scad_code)
            print(f"\n✓ Saved to {filename}")
            return True
        except Exception as e:
            print(f"\n✗ Save failed: {e}")
            return False


# ============================================================================
# COMMAND-LINE INTERFACE
# ============================================================================

def main():
    """Interactive command-line interface"""
    
    print("""
╔════════════════════════════════════════════════════════════╗
║         AUTONOMOUS 3D MODELING AGENT v1.0                  ║
║         Optimized for Bambu Lab A1                         ║
╚════════════════════════════════════════════════════════════╝
""")
    
    # Check for API key
    api_key = Config.ANTHROPIC_API_KEY
    if not api_key:
        print("⚠ ANTHROPIC_API_KEY not found in environment variables")
        api_key = input("Enter your Anthropic API key: ").strip()
    
    # Initialize agent
    agent = ModelAgent(api_key)
    
    print("\nAgent ready! Type 'quit' to exit.\n")
    
    while True:
        try:
            user_input = input("📝 Describe your model: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("\nGoodbye! 👋")
                break
            
            # Process request
            result = agent.process_request(user_input)
            
            # Display results
            print(f"\n{result['message']}")
            
            if result['success']:
                print(f"\n{'─'*60}")
                print("GENERATED OPENSCAD CODE:")
                print(f"{'─'*60}")
                print(result['scad_code'])
                print(f"{'─'*60}")
                
                # Offer to save
                save = input("\n💾 Save to file? (y/n): ").strip().lower()
                if save == 'y':
                    filename = input("Filename [model.scad]: ").strip() or "model.scad"
                    agent.save_model(result['scad_code'], filename)
            
            print()  # Blank line for readability
            
        except KeyboardInterrupt:
            print("\n\nGoodbye! 👋")
            break
        except Exception as e:
            print(f"\n✗ Error: {e}\n")


if __name__ == "__main__":
    main()
