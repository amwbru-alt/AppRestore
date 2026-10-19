"""In-memory AppRevive bearer session; never saves a password/token in app caches."""
import json
import threading
import urllib.request
import urllib.error
from urllib.parse import urlsplit
from .api_config import api_base_url, api_allows_http
from .restoration_codes import RestorationCodeError, promo_ssl_context

_lock = threading.Lock()
_token = ''

class ServiceLoginRequired(RestorationCodeError):
    pass
class ServiceLinkRequired(RestorationCodeError):
    pass

def token():
    with _lock:
        return _token

def set_token(value):
    global _token
    with _lock:
        _token = value

def request(path, body=None):
    url = api_base_url() + path
    parsed = urlsplit(url)
    if parsed.scheme != 'https' and not api_allows_http(url):
        raise RestorationCodeError('Для аккаунта AppRevive нужен HTTPS-адрес API. Пароль не был отправлен. Настройте защищённый адрес сервиса.')
    headers = {'Accept':'application/json','User-Agent':'AppRevive/0.5'}
    current = token()
    if current: headers['Authorization'] = 'Bearer ' + current
    if body is not None: headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(), headers=headers, method='GET' if body is None else 'POST')
    try:
        with urllib.request.urlopen(req, timeout=20, context=promo_ssl_context() if urlsplit(url).scheme=='https' else None) as response:
            raw = response.read(1024*1024+1)
        if len(raw)>1024*1024: raise ValueError('large response')
        result = json.loads(raw)
        if not isinstance(result,dict): raise ValueError('invalid response')
        return result
    except urllib.error.HTTPError as exc:
        try: code=json.loads(exc.read(4096)).get('status','')
        except (ValueError,OSError): code=''
        labels={'https_required':'Для входа в AppRevive требуется HTTPS. Администратор должен настроить защищённый адрес API.',
                'mail_not_configured':'Отправка писем ещё не настроена на сервере.',
                'payments_not_configured':'Приём платежей пока не настроен. Получите код у администратора.',
                'login_failed_or_unverified':'Неверная почта или пароль AppRevive.',
                'account_exists':'Аккаунт с этой почтой уже существует. Войдите с прежним паролем.',
                'password_min_12':'Пароль AppRevive должен содержать от 12 символов.',
                'invalid_or_expired_token':'Ссылка подтверждения недействительна или истекла.',
                'apple_already_linked':'Apple ID уже привязан к другому аккаунту AppRevive.',
                'rate_limited':'Слишком много запросов. Повторите позже.'}
        if exc.code==401: raise ServiceLoginRequired(labels.get(code,'Войдите в аккаунт AppRevive.')) from exc
        if exc.code==403: raise ServiceLinkRequired('Подтвердите почту этого Apple ID в кабинете AppRevive.') from exc
        raise RestorationCodeError(labels.get(code,'Запрос сервиса не выполнен. '+code)) from exc
    except (OSError,ValueError) as exc:
        raise RestorationCodeError('Не удалось связаться с кабинетом AppRevive. Проверьте интернет и адрес API.') from exc
