def test_phase2_imports():
    # Import sanity only. No behavior tests yet.
    from office_app.server.persona_registry import build_default_registry
    from office_app.server.room_router import RoomRouter
    from office_app.server.dialog_contracts import DEFAULT_CONTRACT
    assert build_default_registry() is not None
    assert RoomRouter() is not None
    assert DEFAULT_CONTRACT is not None
