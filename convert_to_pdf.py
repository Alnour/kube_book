#!/usr/bin/env python3
"""
Convert Learning_Kubernetes_Complete.md to PDF using markdown + weasyprint.
Mermaid diagrams are rendered to PNG via mmdc (mermaid-cli) and embedded as
base64 data URIs so WeasyPrint displays them with full text and colors.

Usage:
    python convert_to_pdf.py
    python convert_to_pdf.py input.md output.pdf
"""

import base64
import sys
import os
import re
import shutil
import subprocess
import tempfile
import markdown

from weasyprint import HTML

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INPUT = os.path.join(SCRIPT_DIR, "Learning_Kubernetes_Complete.md")
DEFAULT_OUTPUT = os.path.join(SCRIPT_DIR, "Learning_Kubernetes_Complete.pdf")
MMDC = os.path.join(SCRIPT_DIR, "node_modules", ".bin", "mmdc")

CSS = """
@page {
    size: A4;
    margin: 2.5cm 2cm;
    @bottom-center {
        content: counter(page);
        font-size: 10px;
        color: #666;
    }
}

body {
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 12pt;
    line-height: 1.6;
    color: #1a1a1a;
    max-width: 100%;
}

h1 {
    font-size: 22pt;
    color: #2c3e50;
    border-bottom: 2px solid #326ce5;
    padding-bottom: 8px;
    margin-top: 40px;
    page-break-before: always;
}

h1:first-of-type {
    page-break-before: avoid;
    font-size: 28pt;
    text-align: center;
    border-bottom: 3px solid #326ce5;
}

h2 {
    font-size: 16pt;
    color: #34495e;
    margin-top: 30px;
}

h3 {
    font-size: 14pt;
    color: #2980b9;
    margin-top: 24px;
}

h4 {
    font-size: 12pt;
    color: #2c3e50;
    font-weight: bold;
    margin-top: 20px;
}

p {
    text-align: justify;
    margin-bottom: 10px;
}

ul, ol {
    margin-bottom: 12px;
}

li {
    margin-bottom: 4px;
}

code {
    font-family: 'Courier New', Courier, monospace;
    background-color: #f4f4f4;
    padding: 2px 5px;
    border-radius: 3px;
    font-size: 10pt;
}

pre {
    background-color: #f8f8f8;
    border: 1px solid #ddd;
    border-radius: 5px;
    padding: 12px;
    overflow-x: auto;
    font-size: 9pt;
    line-height: 1.4;
    page-break-inside: avoid;
}

pre code {
    background-color: transparent;
    padding: 0;
}

blockquote {
    border-left: 4px solid #326ce5;
    margin-left: 0;
    padding-left: 16px;
    color: #555;
    font-style: italic;
}

hr {
    border: none;
    border-top: 1px solid #ddd;
    margin: 24px 0;
}

strong {
    color: #2c3e50;
}

table {
    border-collapse: collapse;
    width: 100%;
    margin: 16px 0;
}

th, td {
    border: 1px solid #ddd;
    padding: 8px 12px;
    text-align: left;
}

th {
    background-color: #326ce5;
    color: white;
}

/* Mermaid diagram images */
.mermaid-diagram {
    text-align: center;
    margin: 16px auto;
    page-break-inside: avoid;
}

.mermaid-diagram img {
    max-width: 75%;
    max-height: 400px;
    height: auto;
    width: auto;
}

/* Fallback placeholder if rendering fails */
.mermaid-placeholder {
    background-color: #f0f4f8;
    border: 2px dashed #326ce5;
    border-radius: 8px;
    padding: 16px;
    margin: 16px 0;
    text-align: center;
    color: #555;
    font-style: italic;
    page-break-inside: avoid;
}

/* Figure captions */
p > strong:first-child {
    display: inline;
}
"""


def render_mermaid_blocks(md_text, tmp_dir):
    """Find all mermaid code blocks, render each to PNG, and replace with
    base64-embedded <img> tags that WeasyPrint can display correctly."""
    pattern = re.compile(r'```mermaid\s*\n(.*?)\n```', re.DOTALL)
    matches = list(pattern.finditer(md_text))

    if not matches:
        return md_text

    has_mmdc = os.path.isfile(MMDC) or shutil.which("mmdc")
    if not has_mmdc:
        print("  WARNING: mmdc not found — falling back to placeholders")
        return pattern.sub(
            '<div class="mermaid-placeholder">[Diagram — mmdc not installed]</div>',
            md_text,
        )

    mmdc_cmd = MMDC if os.path.isfile(MMDC) else "mmdc"
    print(f"  Rendering {len(matches)} Mermaid diagrams to PNG...")

    result = md_text
    for i, match in enumerate(reversed(matches)):  # reverse to preserve offsets
        mermaid_src = match.group(1)
        idx = len(matches) - 1 - i  # original index for naming

        input_file = os.path.join(tmp_dir, f"diagram_{idx}.mmd")
        output_file = os.path.join(tmp_dir, f"diagram_{idx}.png")

        with open(input_file, "w", encoding="utf-8") as f:
            f.write(mermaid_src)

        try:
            subprocess.run(
                [mmdc_cmd, "-i", input_file, "-o", output_file,
                 "-b", "white", "-t", "default",
                 "--scale", "2",
                 "-w", "800"],
                check=True,
                capture_output=True,
                timeout=30,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            stderr = getattr(e, "stderr", b"")
            if isinstance(stderr, bytes):
                stderr = stderr.decode(errors="replace")
            print(f"  WARNING: diagram_{idx} failed: {stderr[:200]}")
            replacement = '<div class="mermaid-placeholder">[Diagram could not be rendered]</div>'
            result = result[:match.start()] + replacement + result[match.end():]
            continue

        # Read PNG and encode as base64 data URI
        with open(output_file, "rb") as f:
            png_data = f.read()

        b64 = base64.b64encode(png_data).decode("ascii")
        data_uri = f"data:image/png;base64,{b64}"

        replacement = f'<div class="mermaid-diagram"><img src="{data_uri}" alt="Diagram {idx}"/></div>'
        result = result[:match.start()] + replacement + result[match.end():]

        print(f"    diagram_{idx}: OK ({len(png_data) // 1024} KB)")

    return result


def convert_md_to_pdf(input_path, output_path):
    """Convert a markdown file to PDF."""
    print(f"Reading: {input_path}")
    with open(input_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    # Render mermaid blocks to PNG
    with tempfile.TemporaryDirectory(prefix="mermaid_") as tmp_dir:
        md_text = render_mermaid_blocks(md_text, tmp_dir)

        # Convert markdown to HTML
        print("Converting Markdown to HTML...")
        html_body = markdown.markdown(
            md_text,
            extensions=["extra", "codehilite", "toc", "sane_lists"],
            extension_configs={"codehilite": {"guess_lang": False}},
        )

        # Wrap in full HTML document
        html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8"/>
    <style>{CSS}</style>
</head>
<body>
{html_body}
</body>
</html>"""

        # Convert to PDF
        print(f"Generating PDF: {output_path}")
        HTML(string=html_doc, base_url=SCRIPT_DIR).write_pdf(output_path)
        print(f"Done! PDF saved to: {output_path}")


if __name__ == "__main__":
    input_file = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_INPUT
    output_file = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUTPUT
    convert_md_to_pdf(input_file, output_file)
