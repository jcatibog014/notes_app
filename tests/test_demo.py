"""The create-demo command."""


def run_demo(app, username="demo", password="demo password"):
    runner = app.test_cli_runner()
    return runner.invoke(args=["create-demo", "--username", username, "--password", password])


def test_create_demo_fills_an_account(app, query):
    result = run_demo(app)
    assert result.exit_code == 0, result.output
    user = query("SELECT * FROM users WHERE username = 'demo'")[0]
    assert user["is_demo"] == 1
    notes = query("SELECT * FROM notes WHERE user_id = ?", (user["id"],))
    assert len(notes) >= 6
    assert query("SELECT COUNT(*) AS n FROM note_links")[0]["n"] >= 1


def test_running_it_again_starts_fresh(app, query):
    run_demo(app)
    first = query("SELECT COUNT(*) AS n FROM notes")[0]["n"]
    run_demo(app, password="another password")
    assert query("SELECT COUNT(*) AS n FROM notes")[0]["n"] == first


def test_create_demo_refuses_a_real_account(app, query):
    result = run_demo(app, username="alice")
    assert result.exit_code != 0
    assert "real person" in result.output
    assert query("SELECT is_demo FROM users WHERE username = 'alice'")[0]["is_demo"] == 0
