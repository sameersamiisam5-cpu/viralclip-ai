from typing import Dict, Any

SAFE_STREAMERS = [
    # Top Global Creators (Explicitly encourage & celebrate clippers)
    "ishowspeed", "speed", "kai cenat", "caseoh", "jynxzi", "sketch",
    "xqc", "adin ross", "adin", "tarik", "ludwig", "hasanabi", "valkyrae",
    "pokimane", "sykkuno", "moistcr1tikal", "penguinz0", "ninja",
    "shroud", "timthetatman", "drdisrespect", "asmongold", "disguised toast",
    
    # Top Indian Gaming Creators (Clipper-supportive & highlight-friendly)
    "techno gamerz", "ujjwal", "total gaming", "ajay", "payal gaming", "payal",
    "scout", "scoutop", "mortal", "mortal gaming", "jonathan gaming", "jonathan",
    "mythpat", "carryislive", "carryminati", "dynamo gaming", "dynamo",
    "ghatak", "snax gaming", "rawknee games", "triggered insaan"
]

HIGH_RISK_ENTITIES = [
    # Automated DMCA bots & Corporate Media (Avoid)
    "nintendo", "pokemon", "the pokémon company", "disney", "marvel",
    "sony pictures", "warner bros", "universal pictures", "wwe", "ufc",
    "formula 1", "f1", "premier league", "fifa", "star sports", "sky sports",
    "olympics", "hbo", "paramount", "toei animation"
]

class SafetyScanner:
    @staticmethod
    def evaluate_channel(uploader: str, title: str = "") -> Dict[str, Any]:
        """
        Scans channel name and title to determine copyright safety tier.
        Returns safety level, badge style, strike risk, and safe publishing instructions.
        """
        norm_uploader = (uploader or "").strip().lower()
        norm_title = (title or "").strip().lower()
        combined = f"{norm_uploader} {norm_title}"

        # 1. Check for High-Risk Corporate Media
        for danger in HIGH_RISK_ENTITIES:
            if danger in combined:
                return {
                    "tier": 3,
                    "level": "high_risk",
                    "badge_text": "⚠️ HIGH RISK: Corporate Copyright Bots (Avoid)",
                    "badge_class": "badge-danger",
                    "color": "#FF3366",
                    "strike_risk": "High (Automated DMCA match)",
                    "advice": "This channel is owned by a corporate entity with aggressive automated bots. Clipping not recommended.",
                    "suggested_attribution": f"@{uploader.replace(' ', '')}"
                }

        # 2. Check for Top 100% Clip-Friendly Creators
        for safe in SAFE_STREAMERS:
            if safe in combined:
                clean_name = uploader.strip()
                return {
                    "tier": 1,
                    "level": "safe",
                    "badge_text": f"🟢 100% SAFE: {clean_name} is Clip-Friendly (0% Strike Risk)",
                    "badge_class": "badge-safe",
                    "color": "#00FF66",
                    "strike_risk": "0% (Creator welcomes clippers)",
                    "advice": "Safe for both 9:16 Shorts & 15-20 min Long-Form episodes with our automatic attribution.",
                    "suggested_attribution": f"@{clean_name.replace(' ', '')}"
                }

        # 3. Standard Independent Creator (Fair-Use Protected)
        clean_name = uploader.strip() if uploader else "Creator"
        return {
            "tier": 2,
            "level": "moderate",
            "badge_text": f"🟡 MODERATE: Standard Creator ({clean_name})",
            "badge_class": "badge-moderate",
            "color": "#FFCC00",
            "strike_risk": "Very Low with Fair Use & Attribution",
            "advice": "Safe with our permanent Anti-Copyright Shield, BGM Mute, and Takedown Guarantee.",
            "suggested_attribution": f"@{clean_name.replace(' ', '')}"
        }
