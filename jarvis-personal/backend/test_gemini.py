from backend.ai.gemini_client import ask_gemini


def main():
    response = ask_gemini("Responde solo: JARVIS online")
    print(response)


if __name__ == "__main__":
    main()
