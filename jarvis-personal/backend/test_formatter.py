from backend.ai.response_formatter import format_jarvis_response

data = {
    "debt": {
        "name": "Popular",
        "remaining_amount": 3019742.75,
        "interest_rate": 19.5
    }
}

response = format_jarvis_response(
    user_message="cuál es mi mayor deuda",
    intent="highest_debt",
    data=data
)

print(response)