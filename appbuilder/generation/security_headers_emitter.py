"""Emit the universal generated-application response-header baseline."""

from __future__ import annotations

from pathlib import Path

from .file_writer import write_generated_file
from .utils import _java_file, package_path


def emit_security_headers_source(
    *,
    root_package: str,
    target_profile_name: str,
    output_dir: Path,
    source_manifest: str,
    generation_run_id: str,
) -> Path:
    """Emit the profile-independent security-header filter."""

    output_path = (
        output_dir
        / "src"
        / "main"
        / "java"
        / package_path(root_package)
        / "config"
        / "SecurityHeadersFilter.java"
    )
    return write_generated_file(
        output_path,
        _render_security_headers_filter(
            root_package=root_package,
            target_profile_name=target_profile_name,
            source_manifest=source_manifest,
            generation_run_id=generation_run_id,
        ),
    )


def _render_security_headers_filter(
    *,
    root_package: str,
    target_profile_name: str,
    source_manifest: str,
    generation_run_id: str,
) -> str:
    return _java_file(
        package_name=f"{root_package}.config",
        imports=[
            "jakarta.servlet.FilterChain",
            "jakarta.servlet.ServletException",
            "jakarta.servlet.http.HttpServletRequest",
            "jakarta.servlet.http.HttpServletResponse",
            "java.io.IOException",
            "org.springframework.core.Ordered",
            "org.springframework.core.annotation.Order",
            "org.springframework.stereotype.Component",
            "org.springframework.web.filter.OncePerRequestFilter",
        ],
        body=[
            "@Component",
            "@Order(Ordered.HIGHEST_PRECEDENCE)",
            "public class SecurityHeadersFilter extends OncePerRequestFilter {",
            "",
            "    @Override",
            "    protected void doFilterInternal(",
            "        HttpServletRequest request,",
            "        HttpServletResponse response,",
            "        FilterChain filterChain",
            "    ) throws ServletException, IOException {",
            '        response.setHeader("X-Content-Type-Options", "nosniff");',
            '        response.setHeader("X-Frame-Options", "DENY");',
            '        response.setHeader("Referrer-Policy", "no-referrer");',
            '        response.setHeader("Content-Security-Policy", "frame-ancestors \'none\'");',
            "        filterChain.doFilter(request, response);",
            "    }",
            "}",
        ],
        source_manifest=source_manifest,
        target_profile=target_profile_name,
        generation_run_id=generation_run_id,
    )
