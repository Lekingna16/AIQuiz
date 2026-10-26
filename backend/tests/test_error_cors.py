from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import global_exception_handler


def test_unhandled_error_has_cors_only_for_allowed_origin():
    app = FastAPI()
    app.add_exception_handler(Exception, global_exception_handler)

    @app.get('/failure')
    async def failure():
        raise RuntimeError('test internal failure')

    client = TestClient(app, raise_server_exceptions=False)
    origin = 'https://ai-quiz-blush.vercel.app'
    response = client.get('/failure', headers={'Origin': origin})
    assert response.status_code == 500
    assert response.headers['access-control-allow-origin'] == origin
    assert 'test internal failure' not in response.text
    response = client.get('/failure', headers={'Origin': 'https://untrusted.example'})
    assert 'access-control-allow-origin' not in response.headers
