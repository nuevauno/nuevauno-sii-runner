from __future__ import annotations

import json
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright
from pypdf import PdfReader

from .config import RunnerSettings
from .models import DispatchGuideBatchRequest, DispatchGuideRequest, GuideDefaults, JobResult, PdfArtifact, RuntimeOptions, SiiCredentials


HOST_OVERRIDES = {
    "zeusr.sii.cl": "200.10.252.206",
    "www1.sii.cl": "200.10.251.209",
}


@dataclass
class SessionPaths:
    root: Path
    downloads: Path
    html: Path
    screenshots: Path


def make_paths(root: Path) -> SessionPaths:
    downloads = root / "downloads"
    html = root / "html"
    screenshots = root / "screenshots"
    for item in (root, downloads, html, screenshots):
        item.mkdir(parents=True, exist_ok=True)
    return SessionPaths(root=root, downloads=downloads, html=html, screenshots=screenshots)


def normalize_rut(raw: str) -> tuple[str, str, str]:
    cleaned = re.sub(r"[^0-9kK]", "", raw)
    if len(cleaned) < 2:
        raise ValueError(f"Invalid RUT: {raw}")
    body = cleaned[:-1]
    dv = cleaned[-1].upper()
    return body, dv, f"{int(body):,}".replace(",", ".") + f"-{dv}"


def issue_date_label(value) -> str:
    return value.strftime("%Y-%m-%d")


def save_snapshot(page: Page, paths: SessionPaths, name: str) -> None:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", name).strip("-")
    html_path = paths.html / f"{slug}.html"
    shot_path = paths.screenshots / f"{slug}.png"
    html_path.write_text(page.content(), encoding="utf-8")
    page.screenshot(path=str(shot_path), full_page=True)


def extract_links(page: Page) -> list[dict[str, str]]:
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('a'))
        .map((a) => ({
          text: (a.innerText || a.textContent || '').trim(),
          href: a.href || '',
        }))
        .filter((item) => item.text || item.href)"""
    )


def dump_page_report(page: Page, paths: SessionPaths, name: str) -> None:
    save_snapshot(page, paths, name)
    report = {
        "url": page.url,
        "title": page.title(),
        "links": extract_links(page),
    }
    (paths.root / f"{name}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def set_field(page: Page, selector: str, value: str) -> None:
    locator = page.locator(selector)
    locator.fill(value)
    locator.dispatch_event("change")


def choose_option(page: Page, selector: str, *, value: str | None = None, index: int | None = None) -> None:
    locator = page.locator(selector)
    if value is not None:
        locator.select_option(value=value)
    elif index is not None:
        locator.select_option(index=index)
    else:
        raise ValueError("value or index required")
    locator.dispatch_event("change")


def sync_emitter_origin(page: Page) -> None:
    page.evaluate(
        """() => {
            const f = document.forms['VIEW_EFXP'];
            if (!f) return;
            if (typeof modDir === 'function' && f.elements['EFXP_DIR_ORIGEN']) {
                modDir(f.elements['EFXP_DIR_ORIGEN']);
            }
            const commune = (f.elements['EFXP_CMNA_ORIGEN']?.value || '').trim();
            const cityInput = f.elements['EFXP_CIUDAD_ORIGEN'];
            if (cityInput && !String(cityInput.value || '').trim()) {
                cityInput.value = commune || 'IQUIQUE';
            }
        }"""
    )


def sync_issue_date(page: Page, guide: DispatchGuideRequest) -> None:
    year = guide.issue_date.strftime("%Y")
    month = guide.issue_date.strftime("%m")
    day = guide.issue_date.strftime("%d")
    choose_option(page, "select[name='cbo_dia_boleta']", value=day)
    choose_option(page, "select[name='cbo_mes_boleta']", value=month)
    choose_option(page, "select[name='cbo_anio_boleta']", value=year)
    page.evaluate(
        """({ year, month, day }) => {
            const f = document.forms['VIEW_EFXP'];
            const daySel = f.elements['cbo_dia_boleta'];
            const monthSel = f.elements['cbo_mes_boleta'];
            const yearSel = f.elements['cbo_anio_boleta'];
            daySel.value = day;
            monthSel.value = month;
            yearSel.value = year;
            if (typeof actulizaFecha === 'function') {
                actulizaFecha(daySel);
                actulizaFecha(monthSel);
                actulizaFecha(yearSel);
            }
            f.elements['EFXP_FCH_EMIS'].value = `${year}-${month}-${day}`;
        }""",
        {"year": year, "month": month, "day": day},
    )


def sync_reference_date(page: Page, guide: DispatchGuideRequest, suffix: str = "01") -> None:
    year = guide.issue_date.strftime("%Y")
    month = guide.issue_date.strftime("%m")
    day = guide.issue_date.strftime("%d")
    choose_option(page, f"select[name='cbo_dia_boleta_ref_{suffix}']", value=day)
    choose_option(page, f"select[name='cbo_mes_boleta_ref_{suffix}']", value=month)
    choose_option(page, f"select[name='cbo_anio_boleta_ref_{suffix}']", value=year)
    page.evaluate(
        """({ suffix, year, month, day }) => {
            const f = document.forms['VIEW_EFXP'];
            const daySel = f.elements[`cbo_dia_boleta_ref_${suffix}`];
            const monthSel = f.elements[`cbo_mes_boleta_ref_${suffix}`];
            const yearSel = f.elements[`cbo_anio_boleta_ref_${suffix}`];
            daySel.value = day;
            monthSel.value = month;
            yearSel.value = year;
            if (typeof actulizaFecha === 'function') {
                actulizaFecha(daySel);
                actulizaFecha(monthSel);
                actulizaFecha(yearSel);
            }
            f.elements[`EFXP_FCH_REF_0${suffix}`].value = `${year}-${month}-${day}`;
        }""",
        {"suffix": suffix, "year": year, "month": month, "day": day},
    )


def sync_transfer_type(page: Page, value: str = "6") -> None:
    choose_option(page, "select[name='EFXP_IND_VENTA']", value=value)
    page.evaluate(
        """(value) => {
            const f = document.forms['VIEW_EFXP'];
            if (!f) return;
            if (f.elements['EFXP_IND_VENTA']) {
                f.elements['EFXP_IND_VENTA'].value = value;
            }
            if (f.elements['EFXP_IND_VENTA_DEFUALT']) {
                f.elements['EFXP_IND_VENTA_DEFUALT'].value = value;
            }
        }""",
        value,
    )


def sync_reference_state(page: Page, defaults: GuideDefaults, guide: DispatchGuideRequest) -> None:
    reason = defaults.reference_prefix
    issue_date = guide.issue_date.isoformat()
    page.evaluate(
        """({ reason, issueDate }) => {
            const f = document.forms['VIEW_EFXP'];
            if (!f) return;
            if (f.elements['REF_SI_NO']) {
                f.elements['REF_SI_NO'].checked = true;
            }
            if (typeof RefeneciasChecked !== 'undefined') {
                RefeneciasChecked = 'SiChecked';
            }
            if (f.elements['EFXP_TPO_DOC_REF_001']) {
                f.elements['EFXP_TPO_DOC_REF_001'].value = '802';
            }
            if (f.elements['EFXP_FOLIO_REF_001']) {
                f.elements['EFXP_FOLIO_REF_001'].value = '1';
            }
            if (f.elements['EFXP_FCH_REF_001']) {
                f.elements['EFXP_FCH_REF_001'].value = issueDate;
            }
            if (f.elements['EFXP_RAZON_REF_001']) {
                f.elements['EFXP_RAZON_REF_001'].value = reason;
            }
            if (typeof arrReferencias !== 'undefined' && arrReferencias[0]) {
                arrReferencias[0][0] = '802';
                arrReferencias[0][1] = '';
                arrReferencias[0][2] = '1';
                arrReferencias[0][3] = issueDate;
                arrReferencias[0][4] = '';
                arrReferencias[0][5] = reason;
            }
        }""",
        {"reason": reason, "issueDate": issue_date},
    )


def resolve_host_via_doh(host: str) -> str | None:
    providers = [
        ("https://dns.google/resolve", {}),
        ("https://cloudflare-dns.com/dns-query", {"accept": "application/dns-json"}),
    ]
    for base_url, headers in providers:
        url = f"{base_url}?{urllib.parse.urlencode({'name': host, 'type': 'A'})}"
        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            continue
        answers = payload.get("Answer") or []
        for answer in answers:
            ip = answer.get("data")
            if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", ip or ""):
                return ip
    return None


def browser_host_resolver_rules() -> list[str]:
    rules: list[str] = []
    for host in ("zeusr.sii.cl", "www1.sii.cl"):
        ip = HOST_OVERRIDES.get(host) or resolve_host_via_doh(host)
        if ip:
            rules.append(f"MAP {host} {ip}")
    return rules


def login(page: Page, credentials: SiiCredentials) -> None:
    _, _, formatted_rut = normalize_rut(credentials.username_rut)
    last_error: Exception | None = None
    for _ in range(3):
        try:
            page.goto(credentials.login_url, wait_until="domcontentloaded")
            page.locator("#rutcntr").wait_for(timeout=15000)
            page.locator("#rutcntr").fill(formatted_rut)
            page.locator("#clave").fill(credentials.password)
            page.locator("#bt_ingresar").click()
            page.wait_for_timeout(2500)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            break
        except Exception as exc:
            last_error = exc
            page.wait_for_timeout(1500)
    else:
        raise RuntimeError(f"SII login form did not load after retries: {last_error}")

    if "IngresoRutClave" in page.url:
        raise RuntimeError("SII login did not leave the login page. Check credentials or CAPTCHA requirements.")
    body = page.locator("body").inner_text(timeout=5000)
    if "máximo de sesiones autenticadas" in body.lower():
        raise RuntimeError("SII rejected the login because the account has too many authenticated sessions open.")
    page.wait_for_timeout(1500)
    page.goto(credentials.target_menu_url, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")


def choose_company_if_needed(page: Page, defaults: GuideDefaults) -> None:
    body = page.locator("body").inner_text(timeout=5000)
    if "Seleccione la empresa" not in body and defaults.seller_name not in body:
        return
    seller_match = page.get_by_text(re.compile(re.escape(defaults.seller_name), re.IGNORECASE))
    if seller_match.count():
        seller_match.first.click()
        page.wait_for_load_state("networkidle")
        return
    continue_button = page.get_by_role("button", name=re.compile("continuar|ingresar|aceptar", re.IGNORECASE))
    if continue_button.count():
        continue_button.first.click()
        page.wait_for_load_state("networkidle")


def open_dispatch_guide(page: Page, credentials: SiiCredentials) -> None:
    last_error: Exception | None = None
    for _ in range(3):
        try:
            page.goto(credentials.target_menu_url, wait_until="domcontentloaded")
            page.wait_for_load_state("networkidle")
            page.locator("input[name='EFXP_RUT_RECEP']").wait_for(timeout=15000)
            return
        except Exception as exc:
            last_error = exc
            page.wait_for_timeout(1500)
    raise RuntimeError(f"Dispatch guide form did not load after retries: {last_error}")


def split_rut(raw: str) -> tuple[str, str]:
    body, dv, _ = normalize_rut(raw)
    return body, dv


def fill_recipient(page: Page, defaults: GuideDefaults) -> None:
    rut, dv = split_rut(defaults.recipient_rut)
    set_field(page, "input[name='EFXP_RUT_RECEP']", rut)
    set_field(page, "input[name='EFXP_DV_RECEP']", dv)
    page.locator("input[name='EFXP_DV_RECEP']").dispatch_event("change")
    page.wait_for_timeout(1200)
    set_field(page, "input[name='EFXP_RZN_SOC_RECEP']", defaults.recipient_name)
    dir_select = page.locator("select[name='EFXP_DIR_RECEP']")
    if dir_select.count():
        choose_option(page, "select[name='EFXP_DIR_RECEP']", index=0)
    else:
        set_field(page, "input[name='EFXP_DIR_RECEP']", defaults.recipient_address)
    set_field(page, "input[name='EFXP_CIUDAD_RECEP']", defaults.recipient_city)
    commune_input = page.locator("input[name='EFXP_CMNA_RECEP']")
    if commune_input.count():
        try:
            set_field(page, "input[name='EFXP_CMNA_RECEP']", defaults.recipient_commune)
        except Exception:
            pass
    giro_select = page.locator("select[name='EFXP_GIRO_RECEP']")
    if giro_select.count():
        choose_option(page, "select[name='EFXP_GIRO_RECEP']", index=0)
    else:
        set_field(page, "input[name='EFXP_GIRO_RECEP']", defaults.recipient_business)


def fill_transport(page: Page, defaults: GuideDefaults) -> None:
    rut, dv = split_rut(defaults.transporter_rut)
    set_field(page, "input[name='EFXP_RUT_TRANSPORTE']", rut)
    set_field(page, "input[name='EFXP_DV_TRANSPORTE']", dv)
    set_field(page, "input[name='EFXP_PATENTE']", defaults.vehicle_patent)
    rut, dv = split_rut(defaults.driver_rut)
    set_field(page, "input[name='EFXP_RUT_CHOFER']", rut)
    set_field(page, "input[name='EFXP_DV_CHOFER']", dv)
    set_field(page, "input[name='EFXP_NOMBRE_CHOFER']", defaults.driver_name)


def ensure_detail_line_count(page: Page, count: int) -> None:
    existing = page.locator("input[name^='EFXP_NMB_']").count()
    while existing < count:
        page.locator("input[name='AGREGA_DETALLE']").click()
        page.wait_for_timeout(250)
        existing = page.locator("input[name^='EFXP_NMB_']").count()


def fill_detail_line(page: Page, line_no: int, description: str, units: int, unit_price: int) -> None:
    suffix = f"{line_no:02d}"
    set_field(page, f"input[name='EFXP_NMB_{suffix}']", "TRASLADO NFU")
    desc_toggle = page.locator(f"input[name='DESCRIP_{suffix}']")
    if not desc_toggle.is_checked():
        desc_toggle.check()
        page.wait_for_timeout(150)
    set_field(page, f"textarea[name='EFXP_DSC_ITEM_{suffix}']", description)
    set_field(page, f"input[name='EFXP_QTY_{suffix}']", str(units))
    set_field(page, f"input[name='EFXP_UNMD_{suffix}']", "UN")
    set_field(page, f"input[name='EFXP_PRC_{suffix}']", str(unit_price))
    page.evaluate(
        f"calculaRelacionadoFacEx(document.forms['VIEW_EFXP'].elements['EFXP_QTY_{suffix}'])"
    )


def fill_references(page: Page, defaults: GuideDefaults, guide: DispatchGuideRequest) -> None:
    ref_toggle = page.locator("input[name='REF_SI_NO']")
    if not ref_toggle.is_checked():
        ref_toggle.check()
        page.wait_for_timeout(250)
    choose_option(page, "select[name='EFXP_TPO_DOC_REF_001']", value="802")
    set_field(page, "input[name='EFXP_FOLIO_REF_001']", "1")
    sync_reference_date(page, guide, "01")
    set_field(page, "input[name='EFXP_RAZON_REF_001']", defaults.reference_prefix)
    sync_reference_state(page, defaults, guide)


def fill_known_fields(page: Page, credentials: SiiCredentials, defaults: GuideDefaults, guide: DispatchGuideRequest) -> None:
    sync_emitter_origin(page)
    sync_issue_date(page, guide)
    sync_transfer_type(page, "6")
    fill_recipient(page, defaults)
    fill_transport(page, defaults)
    lines: list[tuple[str, int]] = []
    if guide.auto_units > 0:
        lines.append((defaults.auto_description, guide.auto_units))
    if guide.bus_units > 0:
        lines.append((defaults.bus_description, guide.bus_units))
    if not lines:
        raise RuntimeError(f"{guide.note_label} has no detail lines to emit.")
    ensure_detail_line_count(page, len(lines))
    for index, (description, units) in enumerate(lines, start=1):
        fill_detail_line(page, index, description, units, defaults.unit_price)
    fill_references(page, defaults, guide)
    sync_emitter_origin(page)
    sync_issue_date(page, guide)
    sync_reference_date(page, guide, "01")
    sync_transfer_type(page, "6")
    sync_reference_state(page, defaults, guide)


def validate_and_capture_preview(page: Page, paths: SessionPaths, guide: DispatchGuideRequest) -> None:
    page.get_by_role("button", name="Validar y visualizar").click()
    page.wait_for_timeout(2500)
    page.wait_for_load_state("domcontentloaded")
    dump_page_report(page, paths, f"preview-{issue_date_label(guide.issue_date)}-{guide.note_label}")


def emit_and_download_pdf(
    page: Page,
    paths: SessionPaths,
    guide: DispatchGuideRequest,
    credentials: SiiCredentials,
) -> Path:
    page.get_by_role("button", name=re.compile("Firmar", re.IGNORECASE)).click()
    page.wait_for_load_state("domcontentloaded")
    pwd_fields = page.locator("input[type='password']")
    if not pwd_fields.count():
        raise RuntimeError("Certificate password field did not appear.")
    pwd_fields.first.fill(credentials.certificate_password)
    sign_button = page.get_by_role("button", name=re.compile("Firmar", re.IGNORECASE))
    if sign_button.count():
        sign_button.first.click()
    else:
        page.locator("input[type='submit'], input[type='button']").filter(has_text=re.compile("Firmar", re.IGNORECASE)).first.click()
    page.wait_for_timeout(3000)
    page.wait_for_load_state("domcontentloaded")
    body = page.locator("body").inner_text(timeout=5000)
    if "DOCUMENTO TRIBUTARIO ELECTRÓNICO ENVIADO EXITOSAMENTE" not in body:
        raise RuntimeError("SII did not confirm successful emission.")
    dump_page_report(page, paths, f"sent-{issue_date_label(guide.issue_date)}-{guide.note_label}")
    view_link = page.get_by_role("link", name=re.compile("Ver Documento", re.IGNORECASE))
    if not view_link.count():
        raise RuntimeError("Could not find 'Ver Documento' link after emission.")
    with page.expect_download() as download_info:
        view_link.first.click()
    download = download_info.value
    pdf_path = paths.downloads / f"{issue_date_label(guide.issue_date)}-{guide.note_label}.pdf"
    download.save_as(str(pdf_path))
    return pdf_path


def extract_folio(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    text = "\n".join(page.extract_text() or "" for page in reader.pages[:2])
    match = re.search(r"N[º°]\s*(\d+)", text)
    if not match:
        raise RuntimeError(f"Could not extract folio from {pdf_path.name}")
    return match.group(1)


def final_pdf_name(guide: DispatchGuideRequest, folio: str) -> str:
    parts = [issue_date_label(guide.issue_date), f"Guia{folio}"]
    if guide.auto_units > 0:
        parts.append(f"Auto{guide.auto_units}")
    if guide.bus_units > 0:
        parts.append(f"Bus{guide.bus_units}")
    return "_".join(parts) + ".pdf"


def run_dispatch_guides_job(
    settings: RunnerSettings,
    job_id: str,
    request: DispatchGuideBatchRequest,
) -> JobResult:
    credentials = request.credentials or settings.default_credentials
    defaults = request.defaults or settings.default_guide_defaults
    runtime = request.runtime or settings.default_runtime
    artifact_root = settings.artifacts_dir / job_id
    final_output = artifact_root / "final-pdfs"
    final_output.mkdir(parents=True, exist_ok=True)
    paths = make_paths(artifact_root)
    resolver_rules = browser_host_resolver_rules()
    results: list[PdfArtifact] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=runtime.headless,
            slow_mo=runtime.slow_mo_ms,
            args=[f"--host-resolver-rules={', '.join(resolver_rules)}, EXCLUDE localhost"] if resolver_rules else [],
        )
        context = browser.new_context(
            accept_downloads=True,
            locale="es-CL",
            timezone_id="America/Santiago",
        )
        context.set_default_timeout(runtime.timeout_ms)
        page = context.new_page()
        try:
            login(page, credentials)
            choose_company_if_needed(page, defaults)
            for index, guide in enumerate(request.guides, start=1):
                open_dispatch_guide(page, credentials)
                fill_known_fields(page, credentials, defaults, guide)
                dump_page_report(page, paths, f"run-{index:02d}-filled")
                validate_and_capture_preview(page, paths, guide)
                raw_pdf = emit_and_download_pdf(page, paths, guide, credentials)
                folio = extract_folio(raw_pdf)
                final_name = final_pdf_name(guide, folio)
                final_path = final_output / final_name
                shutil.copy2(raw_pdf, final_path)
                results.append(
                    PdfArtifact(
                        guide=guide.note_label,
                        issue_date=issue_date_label(guide.issue_date),
                        folio=folio,
                        file_name=final_name,
                        file_path=str(final_path),
                    )
                )
                page.goto(credentials.target_menu_url, wait_until="domcontentloaded")
                page.wait_for_timeout(1500)
        finally:
            context.close()
            browser.close()

    (artifact_root / "result.json").write_text(
        json.dumps([item.model_dump() for item in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return JobResult(
        artifacts_dir=str(artifact_root),
        downloads_dir=str(final_output),
        pdfs=results,
    )
