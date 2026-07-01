def generate_label(confidence: float, attribution: str) -> str | None:
    if attribution == "likely_ai":
        ai_pct = round(confidence * 100)
        return (
            f"🤖 **Likely AI-generated — about {ai_pct}% confidence**\n\n"
            "Our analysis suggests this text was probably created with "
            "significant AI assistance. This is an automated estimate, "
            "not a certainty."
        )
    elif attribution == "likely_human":
        human_pct = round((1 - confidence) * 100)
        return (
            f"✍️ **Likely human-written — about {human_pct}% confidence**\n\n"
            "Our analysis found no strong signs of AI generation in this text."
        )
    elif attribution == "uncertain":
        ai_pct = round(confidence * 100)
        return (
            f"❔ **Attribution uncertain — about {ai_pct}% likely AI**\n\n"
            "We couldn't confidently tell whether this was written by a "
            "person or AI, so we're not making a call. Treat the result "
            "as inconclusive."
        )
