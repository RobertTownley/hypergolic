import ssl
import types
from unittest.mock import patch

import pytest

import hypergolic.ssl_bootstrap as sb

_INJECTED_BY_PACKAGE_IMPORT = sb._injected


def test_importing_hypergolic_injects_truststore():
    assert _INJECTED_BY_PACKAGE_IMPORT


def test_ensure_truststore_injects_once_and_is_idempotent():
    with (
        patch.object(sb, "_injected", False),
        patch.object(sb.truststore, "inject_into_ssl") as inject,
    ):
        sb.ensure_truststore()
        sb.ensure_truststore()
    inject.assert_called_once()


@pytest.fixture
def injected():
    sb._injected = False
    sb.ensure_truststore()
    yield


def test_unshadow_covers_every_delegating_setter():
    assert set(sb._unshadow_original_context_setters()) == {
        "minimum_version",
        "maximum_version",
        "options",
        "_msg_callback",
        "verify_flags",
        "verify_mode",
    }, "CPython's ssl.py delegating-setter set changed"


def test_original_context_setters_work_after_injection(injected):
    context = sb._ORIGINAL_SSL_CONTEXT(ssl.PROTOCOL_TLS_CLIENT)
    context.options |= ssl.OP_NO_COMPRESSION
    context.verify_flags |= ssl.VERIFY_X509_STRICT
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.verify_mode = ssl.CERT_REQUIRED


def test_unshadow_repairs_recursive_setters(injected):
    context = sb._ORIGINAL_SSL_CONTEXT(ssl.PROTOCOL_TLS_CLIENT)
    try:
        _reshadow("options")
        with pytest.raises(RecursionError):
            context.options |= ssl.OP_NO_COMPRESSION
    finally:
        sb._unshadow_original_context_setters()
    context.options |= ssl.OP_NO_COMPRESSION


def _reshadow(name: str) -> None:
    """Restore the stock setter, whose `SSLContext` global truststore rebinds."""
    prop = vars(sb._ORIGINAL_SSL_CONTEXT)[name]
    fset = types.FunctionType(
        prop.fset.__code__,
        ssl.__dict__,
        prop.fset.__name__,
        prop.fset.__defaults__,
        prop.fset.__closure__,
    )
    setattr(sb._ORIGINAL_SSL_CONTEXT, name, property(prop.fget, fset, prop.fdel))
