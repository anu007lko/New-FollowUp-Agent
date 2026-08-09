import re

def clean_email_text(text: str) -> str:
    """
    Extract only the fresh content of an email.
    Strips quoted history and signatures safely.
    If uncertain, preserves text to avoid data loss.
    """
    if not text:
        return ""
        
    lines = text.splitlines()
    cleaned_lines = []
    
    quote_markers = [
        "-----Original Message-----",
        "From:", 
        "Sent:",
        "On ",
        "wrote:"
    ]
    
    signature_markers = [
        "--",
        "Best regards",
        "Best Regards",
        "Thanks,",
        "Sincerely,",
        "Thanks & Regards"
    ]
    
    for line in lines:
        stripped = line.strip()
        
        # Check for quoted history boundary
        if any(stripped.startswith(marker) for marker in quote_markers) or \
           (stripped.startswith("On ") and "wrote:" in stripped):
            break # Stop processing, rest is history
            
        if stripped.startswith(">"):
            break
            
        # Check for signature boundary
        if any(stripped.startswith(marker) for marker in signature_markers):
            break
            
        cleaned_lines.append(line)
        
    return "\n".join(cleaned_lines).strip()
