"""
StudyExchange application runner.

Thin entry point exposing the create_app factory and application instance
for local development servers and automated test suites.
"""

from studyexchange import create_app

app = create_app()

if __name__ == '__main__':
    print("==================================================")
    print(" StudyExchange Prototype Server Starting")
    print(" Access: http://127.0.0.1:5000")
    print(" Database automatically initialized.")
    print("==================================================")
    app.run(host='127.0.0.1', port=5000, debug=True)
