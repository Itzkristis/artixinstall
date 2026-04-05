"""
tests/test_init_backends.py
Unit tests for artixinstall's init-backend abstraction + package mapping.
Run: python -m pytest tests/test_init_backends.py -v
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# Mock archinstall (may not be installed in CI)
_ai_mock = MagicMock()
for mod in [
    "archinstall", "archinstall.lib", "archinstall.lib.installer",
    "archinstall.lib.models", "archinstall.lib.output",
    "archinstall.lib.exceptions", "archinstall.lib.plugins",
]:
    sys.modules[mod] = _ai_mock

# Now import our code
from artixinstall.lib.init import InitType, get_backend          # noqa: E402
from artixinstall.lib.init.base import InitBackend, ServiceAction # noqa: E402
from artixinstall.lib.init.openrc import OpenRCBackend           # noqa: E402
from artixinstall.lib.init.runit  import RunitBackend            # noqa: E402
from artixinstall.lib.init.s6     import S6Backend               # noqa: E402
from artixinstall.lib.init.dinit  import DinitBackend            # noqa: E402
from artixinstall.lib.packages    import ArtixPackages, get_full_mapping_table  # noqa: E402
from artixinstall.lib.config      import ArtixConfig             # noqa: E402


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def target(tmp_path):
    return tmp_path

@pytest.fixture(params=list(InitType))
def backend(request, target):
    return get_backend(request.param, target)

def _ok_proc(stdout="ok"):
    p = MagicMock(spec=subprocess.CompletedProcess)
    p.returncode = 0; p.stdout = stdout; p.stderr = ""
    return p

def _fail_proc(stderr="err"):
    p = MagicMock(spec=subprocess.CompletedProcess)
    p.returncode = 1; p.stdout = ""; p.stderr = stderr
    return p


# ── 1. Backend selection ──────────────────────────────────────────────────────

class TestBackendSelection:
    def test_openrc(self, target): assert isinstance(get_backend(InitType.OpenRC, target), OpenRCBackend)
    def test_runit (self, target): assert isinstance(get_backend(InitType.Runit,  target), RunitBackend)
    def test_s6    (self, target): assert isinstance(get_backend(InitType.S6,     target), S6Backend)
    def test_dinit (self, target): assert isinstance(get_backend(InitType.Dinit,  target), DinitBackend)

    def test_unknown_raises(self, target):
        with pytest.raises(ValueError, match="Unknown init type"):
            get_backend("systemd", target)   # type: ignore[arg-type]

    def test_all_types_covered(self, target):
        for it in InitType:
            assert isinstance(get_backend(it, target), InitBackend)


# ── 2. Properties ─────────────────────────────────────────────────────────────

class TestBackendProperties:
    def test_name_nonempty         (self, backend): assert backend.name
    def test_base_pkgs_nonempty    (self, backend): assert len(backend.base_packages) >= 2
    def test_time_sync_nonempty    (self, backend): assert backend.time_sync_service
    def test_time_sync_pkgs        (self, backend): assert backend.time_sync_packages

    def test_no_systemd_in_base    (self, backend):
        for p in backend.base_packages:
            assert "systemd" not in p

    def test_no_timesyncd_in_sync  (self, backend):
        assert "timesyncd" not in backend.time_sync_service
        for p in backend.time_sync_packages:
            assert "timesyncd" not in p


# ── 3. _clean_name ────────────────────────────────────────────────────────────

class TestCleanName:
    @pytest.mark.parametrize("raw,expected", [
        ("NetworkManager.service", "NetworkManager"),
        ("fstrim.timer",           "fstrim"),
        ("cups.socket",            "cups"),
        ("multi-user.target",      "multi-user"),
        ("sshd",                   "sshd"),
    ])
    def test_clean(self, backend, raw, expected):
        assert backend._clean_name(raw) == expected


# ── 4. Package mapping ────────────────────────────────────────────────────────

class TestPackageMapping:
    @pytest.mark.parametrize("it", list(InitType))
    def test_systemd_is_none          (self, it): assert ArtixPackages(it).resolve("systemd") is None
    @pytest.mark.parametrize("it", list(InitType))
    def test_timesyncd_replaced       (self, it):
        r = ArtixPackages(it).resolve("systemd-timesyncd")
        assert r and "timesyncd" not in r
    @pytest.mark.parametrize("it", list(InitType))
    def test_nm_gets_suffix           (self, it):
        r = ArtixPackages(it).resolve("networkmanager")
        assert r and it.value in r
    @pytest.mark.parametrize("it", list(InitType))
    def test_unknown_passthrough      (self, it): assert ArtixPackages(it).resolve("htop") == "htop"
    @pytest.mark.parametrize("it", list(InitType))
    def test_base_no_systemd          (self, it):
        for p in ArtixPackages(it).base_system():
            assert "systemd" not in p
    @pytest.mark.parametrize("it", list(InitType))
    def test_base_has_init_pkg        (self, it):
        assert any(it.value in p for p in ArtixPackages(it).base_system())
    def test_resolve_many_drops_none  (self):
        r = ArtixPackages(InitType.OpenRC).resolve_many(["htop", "systemd", "vim"])
        assert "systemd" not in r and "htop" in r
    def test_mapping_table_structure  (self):
        t = get_full_mapping_table()
        assert len(t) > 5
        for row in t:
            for key in ("arch","state","openrc","runit","s6","dinit"):
                assert key in row


# ── 5. OpenRC idempotent enable ───────────────────────────────────────────────

class TestOpenRCIdempotent:
    def test_already_in_runlevel_is_success(self, target):
        b = OpenRCBackend(target)
        proc = _fail_proc("* NetworkManager already in runlevel default")
        with patch.object(b, "_chroot", return_value=proc):
            r = b.enable_service("NetworkManager")
        assert r.success is True


# ── 6. Runit missing sv dir ───────────────────────────────────────────────────

class TestRunitMissingSv:
    def test_missing_sv_dir_clear_error(self, target):
        b = RunitBackend(target)
        proc = _ok_proc("sv dir missing: /etc/runit/sv/nonexistent")
        with patch.object(b, "_chroot", return_value=proc):
            r = b.enable_service("nonexistent")
        assert r.success is False
        assert "runit service dir" in r.message


# ── 7. ArtixConfig serialisation ─────────────────────────────────────────────

class TestArtixConfig:
    def test_default_is_openrc(self):
        assert ArtixConfig().init_type == InitType.OpenRC

    @pytest.mark.parametrize("it", list(InitType))
    def test_json_roundtrip(self, it):
        assert ArtixConfig.from_json(ArtixConfig(init_type=it).json()).init_type == it

    def test_unknown_init_defaults_openrc(self):
        assert ArtixConfig.from_json({"init_type": "bogus"}).init_type == InitType.OpenRC

    def test_save_load(self, tmp_path):
        cfg = ArtixConfig(init_type=InitType.Dinit, include_lib32=True)
        cfg.save(tmp_path / "cfg.json")
        loaded = ArtixConfig.from_file(tmp_path / "cfg.json")
        assert loaded.init_type == InitType.Dinit
        assert loaded.include_lib32 is True


# ── 8. Subprocess dispatch ────────────────────────────────────────────────────

class TestDispatch:
    def test_openrc_enable_rc_update_add(self, target):
        b = OpenRCBackend(target)
        with patch.object(b, "_chroot", return_value=_ok_proc()) as m:
            b.enable_service("sshd")
        m.assert_called_once_with(["rc-update", "add", "sshd", "default"])

    def test_openrc_disable_rc_update_del(self, target):
        b = OpenRCBackend(target)
        with patch.object(b, "_chroot", return_value=_ok_proc()) as m:
            b.disable_service("sshd.service")
        m.assert_called_once_with(["rc-update", "del", "sshd"])

    def test_runit_enable_has_ln_sf(self, target):
        b = RunitBackend(target)
        with patch.object(b, "_chroot", return_value=_ok_proc("enabled")) as m:
            b.enable_service("NetworkManager")
        assert "ln -sf" in " ".join(m.call_args[0][0])

    def test_dinit_enable_boot_d(self, target):
        b = DinitBackend(target)
        with patch.object(b, "_chroot", return_value=_ok_proc()) as m:
            b.enable_service("sddm")
        cmd = " ".join(m.call_args[0][0])
        assert "ln -sf" in cmd and "boot.d" in cmd

    def test_s6_enable_touch_adminsv(self, target):
        b = S6Backend(target)
        with patch.object(b, "_chroot", return_value=_ok_proc()) as m:
            b.enable_service("openntpd")
        cmd = " ".join(m.call_args[0][0])
        assert "touch" in cmd and "adminsv" in cmd


# ── 9. Batch enable ───────────────────────────────────────────────────────────

class TestBatchEnable:
    def test_enable_services_list(self, target):
        b = OpenRCBackend(target)
        calls = []
        from artixinstall.lib.init.base import ServiceResult
        def fake(svc, runlevel="default"):
            calls.append(svc)
            return ServiceResult(svc, ServiceAction.ENABLE, True)
        with patch.object(b, "enable_service", side_effect=fake):
            b.enable_services(["sshd", "cronie", "NetworkManager"])
        assert calls == ["sshd", "cronie", "NetworkManager"]


# ── 10. Network packages ──────────────────────────────────────────────────────

class TestNetworkPackages:
    @pytest.mark.parametrize("it", list(InitType))
    def test_nm_includes_suffix(self, it):
        pkgs = ArtixPackages(it).networking_packages(use_nm=True)
        assert "networkmanager" in pkgs
        assert any(it.value in p for p in pkgs)

    @pytest.mark.parametrize("it", list(InitType))
    def test_dhcpcd_includes_suffix(self, it):
        pkgs = ArtixPackages(it).networking_packages(use_nm=False)
        assert "dhcpcd" in pkgs
        assert any(it.value in p for p in pkgs)
