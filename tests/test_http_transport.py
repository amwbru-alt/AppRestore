import io
import json
import pytest
from apprevive_core import api_config, service_session, account_credits


def test_explicit_http_permission_is_limited_to_exact_origin(monkeypatch):
    monkeypatch.setenv('APPREVIVE_HTTP_AUTH_ORIGIN', 'http://185.173.93.200:3000')
    assert api_config.api_allows_http('http://185.173.93.200:3000/v3/me')
    assert not api_config.api_allows_http('http://185.173.93.200:3001/v3/me')
    assert not api_config.api_allows_http('http://203.0.113.50:3000/v3/me')
    assert not api_config.api_allows_http('https://185.173.93.200:3000/v3/me')


def test_service_and_balance_use_authorized_http_transport(monkeypatch):
    target='http://185.173.93.200:3000'
    monkeypatch.setenv('APPREVIVE_HTTP_AUTH_ORIGIN', target)
    calls=[]
    def fetch(req, **options):
        calls.append((req,options))
        return io.BytesIO(json.dumps({'status':'ok','account_id':'a'*64,'credits':1}).encode())
    monkeypatch.setattr(service_session,'api_base_url',lambda:target)
    monkeypatch.setattr(account_credits,'api_base_url',lambda:target)
    monkeypatch.setattr(service_session.urllib.request,'urlopen',fetch)
    service_session.set_token('b'*64)
    try:
        service_session.request('/v3/me')
        account_credits.api_call('balance',{'account_id':'a'*64})
    finally:service_session.set_token('')
    assert len(calls)==2
    assert all(req.full_url.startswith(target) and options['context'] is None for req,options in calls)
    assert all(req.get_header('Authorization')=='Bearer '+'b'*64 for req,_ in calls)
