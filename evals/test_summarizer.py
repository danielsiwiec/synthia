import pytest

from synthia.agents.claude import InitMessage, Result, ToolCall
from synthia.agents.learning.learner import Learner


@pytest.mark.asyncio
async def test_summarizer_happy_path():
    learner = Learner()

    # First session: Task counting
    session1_id = "3ac245a2-ac19-4046-bf46-42233056892d"
    session1_messages = [
        InitMessage(
            session_id=session1_id,
            prompt=(
                "list files in current folder, then for each file smaller than 1MB "
                "count the number of occurances of the word task in it and return the total"
            ),
        ),
        ToolCall(
            session_id=session1_id,
            name="Bash",
            input={"command": "ls -lh", "description": "List files with sizes in current directory"},
            output=(
                "total 416\n-rw-r--r--@  1 dansiwiec  staff   405B Oct  3 15:29 Makefile\n"
                "-rw-r--r--@  1 dansiwiec  staff   888B Oct  3 14:11 README.md"
            ),
        ),
        ToolCall(
            session_id=session1_id,
            name="Bash",
            input={"command": 'grep -io "task" README.md | wc -l', "description": "Count 'task' in README.md"},
            output="4",
        ),
        ToolCall(
            session_id=session1_id,
            name="Bash",
            input={"command": 'grep -io "task" Makefile | wc -l', "description": "Count 'task' in Makefile"},
            output="0",
        ),
        Result(
            session_id=session1_id,
            success=True,
            result=(
                '**Total: 4**\n\nThe word "task" appears 4 times total across all files smaller than 1MB '
                "in the current directory "
                "(all occurrences were in README.md)."
            ),
        ),
    ]

    # Second session: Similar file operations
    session2_id = "4bc356b3-bd20-5157-cg57-53344167903e"
    session2_messages = [
        InitMessage(
            session_id=session2_id, prompt="find all Python files and count occurrences of the word import in each file"
        ),
        ToolCall(
            session_id=session2_id,
            name="Bash",
            input={"command": "find . -name '*.py'", "description": "Find all Python files"},
            output="./main.py\n./utils.py\n./test_file.py",
        ),
        ToolCall(
            session_id=session2_id,
            name="Bash",
            input={"command": 'grep -c "import" main.py', "description": "Count 'import' in main.py"},
            output="3",
        ),
        ToolCall(
            session_id=session2_id,
            name="Bash",
            input={"command": 'grep -c "import" utils.py', "description": "Count 'import' in utils.py"},
            output="2",
        ),
        Result(session_id=session2_id, success=True, result="Found 5 total import statements across 2 Python files."),
    ]

    # Third session: Another similar pattern
    session3_id = "5cd467c4-ce31-6268-dh68-64455278014f"
    session3_messages = [
        InitMessage(
            session_id=session3_id, prompt="search for all JavaScript files and count function definitions in each"
        ),
        ToolCall(
            session_id=session3_id,
            name="Bash",
            input={"command": "find . -name '*.js'", "description": "Find all JavaScript files"},
            output="./app.js\n./utils.js\n./components.js",
        ),
        ToolCall(
            session_id=session3_id,
            name="Bash",
            input={"command": 'grep -c "function " app.js', "description": "Count functions in app.js"},
            output="4",
        ),
        ToolCall(
            session_id=session3_id,
            name="Bash",
            input={"command": 'grep -c "function " utils.js', "description": "Count functions in utils.js"},
            output="2",
        ),
        Result(
            session_id=session3_id, success=True, result="Found 6 total function definitions across 2 JavaScript files."
        ),
    ]

    # Process first session
    for message in session1_messages:
        await learner.process_message(message)

    # Process second session
    for message in session2_messages:
        await learner.process_message(message)

    # Process third session
    for message in session3_messages:
        await learner.process_message(message)
