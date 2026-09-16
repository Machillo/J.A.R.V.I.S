from backend.ai.jarvis_engine import process_message

def main():
    tests = [
        "cuál es mi mayor deuda",
        "cuánto me falta para Ecuador",
        "cómo estoy financieramente",
        "qué hábitos de gasto tengo",
    ]

    for test in tests:
        print("USER:", test)
        result = process_message(test)
        print("JARVIS:", result["message"])
        print("INTENT:", result["intent"])
        print("---")


if __name__ == "__main__":
    main()
