#!/usr/bin/env python3
"""
Convert Kubernetes book Markdown files to LaTeX.

Reads individual chapter Markdown files and generates a complete LaTeX book
project in the latex/ directory, including:
  - main.tex, preamble.tex, frontmatter.tex
  - Chapter .tex files (summary, ch1-ch6, conclusion)
  - references.bib
  - figures/*.tex (TikZ diagrams)
  - Makefile

Usage:
    python convert_to_latex.py
"""

import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "latex")
FIGURES_DIR = os.path.join(OUTPUT_DIR, "figures")

# Source files: (output_key, markdown_filename, figure_prefix)
CHAPTERS = [
    ("summary",    "Summary.md",              "S"),
    ("ch1",        "Chapter_1_Expanded.md",    "1"),
    ("ch2",        "Chapter_2_Expanded.md",    "2"),
    ("ch3",        "Chapter_3_Expanded.md",    "3"),
    ("ch4",        "Chapter_4_Expanded.md",    "4"),
    ("ch5",        "Chapter_5_Expanded.md",    "5"),
    ("ch6",        "Chapter_6_Expanded.md",    "6"),
    ("conclusion", "Conclusion_Expanded.md",   "C"),
]


# ---------------------------------------------------------------------------
# LaTeX escaping & inline conversion
# ---------------------------------------------------------------------------

def escape_latex(text):
    """Escape LaTeX special characters in plain text."""
    # Order matters: backslash first, then others
    text = text.replace("\\", "\\textbackslash{}")
    text = text.replace("&", "\\&")
    text = text.replace("%", "\\%")
    text = text.replace("$", "\\$")
    text = text.replace("#", "\\#")
    text = text.replace("{", "\\{")
    text = text.replace("}", "\\}")
    text = text.replace("~", "\\textasciitilde{}")
    text = text.replace("^", "\\textasciicircum{}")
    text = text.replace("_", "\\_")
    # Typographic improvements
    text = text.replace("---", "---")  # em-dash already fine in LaTeX
    text = text.replace("--", "--")
    return text


def convert_inline(text):
    """Convert inline Markdown formatting to LaTeX."""
    if not text.strip():
        return text

    # 1. Protect code spans
    code_spans = []
    def save_code(m):
        code_spans.append(m.group(1))
        return f"\x00CODE{len(code_spans)-1}\x00"
    text = re.sub(r'`([^`]+)`', save_code, text)

    # 2. Protect links [text](url)
    links = []
    def save_link(m):
        links.append((m.group(1), m.group(2)))
        return f"\x00LINK{len(links)-1}\x00"
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', save_link, text)

    # 3. Escape LaTeX special chars in remaining text
    text = escape_latex(text)

    # 4. Convert bold **text** -> \textbf{text}  (before italic)
    text = re.sub(r'\*\*(.+?)\*\*', r'\\textbf{\1}', text)

    # 5. Convert italic *text* -> \textit{text}
    text = re.sub(r'\*(.+?)\*', r'\\textit{\1}', text)

    # 6. Restore code spans as \code{...}
    for i, code in enumerate(code_spans):
        escaped = code.replace("\\", "\\textbackslash{}")
        escaped = escaped.replace("_", "\\_")
        escaped = escaped.replace("&", "\\&")
        escaped = escaped.replace("%", "\\%")
        escaped = escaped.replace("$", "\\$")
        escaped = escaped.replace("#", "\\#")
        escaped = escaped.replace("{", "\\{")
        escaped = escaped.replace("}", "\\}")
        escaped = escaped.replace("~", "\\textasciitilde{}")
        # Wrap in \code{} but need real braces
        text = text.replace(f"\x00CODE{i}\x00", "\\code{" + escaped + "}")

    # 7. Restore links as \href{url}{text}
    for i, (label, url) in enumerate(links):
        escaped_label = escape_latex(label)
        # URLs need minimal escaping (mainly # and %)
        safe_url = url.replace("%", "\\%").replace("#", "\\#")
        safe_url = safe_url.replace("_", "\\_")
        text = text.replace(f"\x00LINK{i}\x00",
                            "\\href{" + safe_url + "}{" + escaped_label + "}")

    # 8. Handle em-dashes: " — " (unicode em-dash)
    text = text.replace(" — ", " --- ")
    text = text.replace("—", "---")

    return text


# ---------------------------------------------------------------------------
# Chapter processing (state-machine parser)
# ---------------------------------------------------------------------------

def process_chapter(md_text, fig_prefix, is_summary=False):
    """Convert chapter Markdown to LaTeX body content.

    Returns LaTeX string for the chapter body (no \\chapter command for summary,
    uses \\chapter for expanded chapters).
    """
    # Preprocess: ensure code fences start on their own line
    md_text = re.sub(r'(\S[ \t]*)```(mermaid)', r'\1\n```\2', md_text)
    md_text = re.sub(r'(\S[ \t]*)```(\w+)', r'\1\n```\2', md_text)

    lines = md_text.split("\n")
    output = []
    state = "NORMAL"  # NORMAL, IN_MERMAID, IN_CODE
    fig_counter = 0
    mermaid_just_closed = False
    list_env_stack = []  # stack of 'itemize' or 'enumerate'
    in_references = False
    skip_chapter_title = True  # skip first # heading (chapter title handled elsewhere)
    code_language = "bash"
    pending_blank = False  # delay list closing on blank lines

    def close_all_lists():
        nonlocal list_env_stack
        while list_env_stack:
            env = list_env_stack.pop()
            output.append(f"\\end{{{env}}}")

    def ensure_list_depth(target_depth, env_type):
        nonlocal list_env_stack
        current_depth = len(list_env_stack)
        while current_depth > target_depth:
            e = list_env_stack.pop()
            output.append(f"\\end{{{e}}}")
            current_depth -= 1
        if current_depth < target_depth:
            list_env_stack.append(env_type)
            output.append(f"\\begin{{{env_type}}}")

    for line in lines:
        stripped = line.strip()

        # --- IN_MERMAID state ---
        if state == "IN_MERMAID":
            if stripped.startswith("```"):
                state = "NORMAL"
                mermaid_just_closed = True
            continue

        # --- IN_CODE state ---
        if state == "IN_CODE":
            if stripped.startswith("```"):
                output.append("\\end{lstlisting}")
                output.append("")
                state = "NORMAL"
            else:
                output.append(line)  # raw, no escaping in code blocks
            continue

        # --- NORMAL state ---

        # Skip references section
        if stripped == "## References" or stripped == "## References:":
            close_all_lists()
            in_references = True
            continue
        if in_references:
            # Check if we hit a new section that ends references
            if stripped.startswith("## ") or stripped.startswith("# "):
                in_references = False
            else:
                continue

        # Start of mermaid block
        if stripped.startswith("```mermaid"):
            close_all_lists()
            state = "IN_MERMAID"
            fig_counter += 1
            continue

        # Start of code block
        if stripped.startswith("```"):
            close_all_lists()
            lang_match = re.match(r'```(\w+)', stripped)
            code_language = lang_match.group(1) if lang_match else ""
            # Map common languages
            lang_map = {
                "yaml": "yaml", "yml": "yaml",
                "python": "Python", "py": "Python",
                "bash": "bash", "sh": "bash",
                "json": "json", "go": "Go",
                "java": "Java", "javascript": "JavaScript",
            }
            display_lang = lang_map.get(code_language.lower(), code_language)
            if display_lang:
                output.append(f"\\begin{{lstlisting}}[language={display_lang}]")
            else:
                output.append("\\begin{lstlisting}")
            state = "IN_CODE"
            continue

        # Figure caption line (follows mermaid block)
        fig_caption_match = re.match(r'\*\*Figure\s+[\w.]+:\*\*\s*(.*)', stripped)
        if fig_caption_match and mermaid_just_closed:
            caption_text = fig_caption_match.group(1).strip()
            caption_text = convert_inline(caption_text)
            fig_file = f"fig{fig_prefix}_{fig_counter}"
            output.append("\\begin{figure}[htbp]")
            output.append("\\centering")
            output.append(f"\\input{{figures/{fig_file}}}")
            output.append(f"\\caption{{{caption_text}}}")
            output.append(f"\\label{{fig:{fig_prefix}_{fig_counter}}}")
            output.append("\\end{figure}")
            output.append("")
            mermaid_just_closed = False
            continue

        # Clear mermaid flag on non-empty, non-caption lines
        if stripped and mermaid_just_closed:
            mermaid_just_closed = False

        # Check for list items (needed for blank-line logic below)
        bullet_match = re.match(r'^(\s*)[*\-]\s+(.*)', line)
        numbered_match = re.match(r'^(\s*)\d+\.\s+(.*)', line)

        # Flush pending blank: close lists only if the next line is NOT a list item
        if pending_blank and stripped:
            pending_blank = False
            if not (bullet_match or numbered_match):
                close_all_lists()
                output.append("")

        # Horizontal rules -> skip
        if stripped == "---":
            pending_blank = False
            close_all_lists()
            continue

        # Headings
        heading_match = re.match(r'^(#{1,4})\s+(.*)', stripped)
        if heading_match:
            close_all_lists()
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()

            if level == 1:
                if skip_chapter_title and not is_summary:
                    skip_chapter_title = False
                    # Emit chapter command
                    # Extract chapter title (remove "Chapter X (Expanded): " prefix)
                    clean_title = re.sub(
                        r'^Chapter\s+\d+\s*\(Expanded\)\s*:\s*', '', title)
                    clean_title = re.sub(
                        r'^Conclusion and Future Trajectories$',
                        'Conclusion and Future Trajectories', clean_title)
                    output.append(f"\\chapter{{{convert_inline(clean_title)}}}")
                elif is_summary:
                    skip_chapter_title = False
                    continue  # skip title lines in summary
                else:
                    output.append(f"\\chapter{{{convert_inline(title)}}}")
            elif level == 2:
                if is_summary and "Introduction" in title:
                    # For summary, the Introduction section IS the chapter
                    output.append(f"\\chapter{{{convert_inline('Introduction: What is Kubernetes and Why Does It Exist?')}}}")
                else:
                    output.append(f"\\section{{{convert_inline(title)}}}")
            elif level == 3:
                output.append(f"\\subsection{{{convert_inline(title)}}}")
            elif level == 4:
                output.append(f"\\subsubsection{{{convert_inline(title)}}}")
            output.append("")
            continue

        # Blank line
        if not stripped:
            if mermaid_just_closed:
                continue  # skip blank lines between mermaid and caption
            if list_env_stack:
                # In a list: defer closing until we see what comes next
                pending_blank = True
            else:
                output.append("")
            continue

        # List items
        if bullet_match:
            indent = len(bullet_match.group(1))
            content = bullet_match.group(2)
            depth = indent // 4 + 1
            ensure_list_depth(depth, "itemize")
            output.append(f"\\item {convert_inline(content)}")
            continue

        if numbered_match:
            indent = len(numbered_match.group(1))
            content = numbered_match.group(2)
            depth = indent // 4 + 1
            ensure_list_depth(depth, "enumerate")
            output.append(f"\\item {convert_inline(content)}")
            continue

        # Regular paragraph text
        close_all_lists()
        output.append(convert_inline(stripped))

    close_all_lists()
    return "\n".join(output)


def process_summary(md_text):
    """Process Summary.md — extract only the Introduction section."""
    # Find the Introduction section
    intro_start = md_text.find("## Introduction:")
    if intro_start == -1:
        intro_start = md_text.find("## Introduction")
    if intro_start == -1:
        print("WARNING: Could not find Introduction in Summary.md")
        return ""

    # Find end of introduction (next ## Chapter heading or --- before it)
    intro_end = md_text.find("\n## Chapter 1:", intro_start + 1)
    if intro_end == -1:
        intro_end = len(md_text)

    # Also include any content before the next --- after intro
    intro_text = md_text[intro_start:intro_end].rstrip()

    # Remove trailing --- if present
    if intro_text.endswith("---"):
        intro_text = intro_text[:-3].rstrip()

    return process_chapter(intro_text, "S", is_summary=True)


def extract_frontmatter(md_text):
    """Extract title, authors, and acknowledgments from Summary.md."""
    lines = md_text.split("\n")
    title = ""
    authors = ""
    acknowledgments = []
    in_ack = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# Learning Kubernetes"):
            title = stripped.lstrip("# ").strip()
        elif stripped.startswith("- Authors:"):
            authors = stripped.replace("- Authors:", "").strip()
        elif stripped == "## Acknowledgments":
            in_ack = True
        elif in_ack and stripped.startswith("## "):
            in_ack = False
        elif in_ack and stripped.startswith("- "):
            acknowledgments.append(stripped[2:])

    return title, authors, acknowledgments


# ---------------------------------------------------------------------------
# Structural file generators
# ---------------------------------------------------------------------------

def generate_preamble():
    return r"""\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage[a4paper, margin=2.5cm]{geometry}
\usepackage{graphicx}
\usepackage{xcolor}
\usepackage{hyperref}
\usepackage{bookmark}
\usepackage{amsmath, amssymb}

% TikZ
\usepackage{tikz}
\usetikzlibrary{
  shapes.geometric,
  arrows.meta,
  positioning,
  calc,
  fit,
  backgrounds,
  decorations.pathreplacing,
  patterns
}

% pgfplots for bar charts
\usepackage{pgfplots}
\pgfplotsset{compat=1.18}

% Code listings
\usepackage{listings}
\lstset{
  basicstyle=\ttfamily\small,
  breaklines=true,
  breakatwhitespace=false,
  frame=single,
  backgroundcolor=\color{codebg},
  rulecolor=\color{codeframe},
  numbers=none,
  tabsize=2,
  showstringspaces=false,
  captionpos=b,
  aboveskip=10pt,
  belowskip=10pt,
  xleftmargin=4pt,
  xrightmargin=4pt,
  framexleftmargin=2pt,
  columns=flexible,
  literate={-}{-}1,
}

% YAML language definition for listings
\lstdefinelanguage{yaml}{
  keywords={true,false,null,yes,no},
  sensitive=false,
  comment=[l]{\#},
  morestring=[b]',
  morestring=[b]",
}

% Bibliography
\usepackage[backend=biber, style=authoryear, sorting=nyt, maxbibnames=99]{biblatex}
\addbibresource{references.bib}

% Fancy headers
\usepackage{fancyhdr}
\pagestyle{fancy}
\fancyhf{}
\fancyhead[LE]{\leftmark}
\fancyhead[RO]{\rightmark}
\fancyfoot[C]{\thepage}
\renewcommand{\headrulewidth}{0.4pt}

% Chapter styling
\usepackage{titlesec}
\titleformat{\chapter}[display]
  {\normalfont\huge\bfseries\color{darkblue}}
  {\chaptertitlename\ \thechapter}{20pt}{\Huge}
\titlespacing*{\chapter}{0pt}{-20pt}{30pt}

% Section colors
\titleformat{\section}{\normalfont\Large\bfseries\color{sectioncolor}}{\thesection}{1em}{}
\titleformat{\subsection}{\normalfont\large\bfseries\color{oceanblue}}{\thesubsection}{1em}{}
\titleformat{\subsubsection}{\normalfont\normalsize\bfseries\color{darkblue}}{\thesubsubsection}{1em}{}

% -----------------------------------------------------------------------
% Color definitions (matching Mermaid palette)
% -----------------------------------------------------------------------
\definecolor{darkblue}{HTML}{2C3E50}
\definecolor{k8sgreen}{HTML}{27AE60}
\definecolor{k8sred}{HTML}{E74C3C}
\definecolor{oceanblue}{HTML}{2980B9}
\definecolor{k8spurple}{HTML}{8E44AD}
\definecolor{k8sorange}{HTML}{E67E22}
\definecolor{k8sgray}{HTML}{7F8C8D}
\definecolor{lightgray}{HTML}{95A5A6}
\definecolor{silvergray}{HTML}{BDC3C7}
\definecolor{cloudgray}{HTML}{ECF0F1}
\definecolor{sectioncolor}{HTML}{34495E}
\definecolor{k8sblue}{HTML}{326CE5}
\definecolor{codebg}{HTML}{F8F8F8}
\definecolor{codeframe}{HTML}{DDDDDD}
\definecolor{warnorange}{HTML}{F39C12}
\definecolor{darkred}{HTML}{C0392B}

% -----------------------------------------------------------------------
% Reusable TikZ styles
% -----------------------------------------------------------------------
\tikzset{
  mnode/.style={
    rectangle, rounded corners=4pt, minimum width=2.2cm,
    minimum height=0.9cm, text centered, font=\small,
    draw=none, text=white, inner sep=4pt,
  },
  darkblue node/.style={mnode, fill=darkblue},
  green node/.style={mnode, fill=k8sgreen},
  red node/.style={mnode, fill=k8sred},
  blue node/.style={mnode, fill=oceanblue},
  purple node/.style={mnode, fill=k8spurple},
  orange node/.style={mnode, fill=k8sorange},
  gray node/.style={mnode, fill=k8sgray},
  lightgray node/.style={mnode, fill=lightgray, text=darkblue},
  silver node/.style={mnode, fill=silvergray, text=darkblue},
  cloud node/.style={mnode, fill=cloudgray, text=darkblue},
  k8sblue node/.style={mnode, fill=k8sblue},
  warn node/.style={mnode, fill=warnorange},
  subgraph/.style={
    draw=gray, dashed, rounded corners=6pt, inner sep=10pt,
    fill=none, label={[font=\small\bfseries, anchor=north west]north west:#1},
  },
  arr/.style={-{Stealth[length=6pt]}, thick},
  darr/.style={<->{Stealth[length=6pt]}, thick},
}

% -----------------------------------------------------------------------
% Custom commands
% -----------------------------------------------------------------------
\newcommand{\code}[1]{\texttt{#1}}
"""


def generate_main_tex():
    return r"""\documentclass[11pt, a4paper, openany]{book}

\input{preamble}

\begin{document}

\input{frontmatter}

\mainmatter

\input{summary}
\input{ch1}
\input{ch2}
\input{ch3}
\input{ch4}
\input{ch5}
\input{ch6}
\input{conclusion}

\backmatter
\printbibliography[heading=bibintoc, title={References}]

\end{document}
"""


def generate_frontmatter(title, authors, acknowledgments):
    ack_lines = "\n".join(
        f"\\item {escape_latex(a)}" for a in acknowledgments
    )
    # Split title into main title and subtitle at the colon
    if ":" in title:
        main_title, subtitle = title.split(":", 1)
        main_title = main_title.strip()
        subtitle = subtitle.strip()
    else:
        main_title = title
        subtitle = ""
    return rf"""\frontmatter

% Title page
\begin{{titlepage}}
\centering
\vspace*{{3cm}}

{{\Huge\bfseries\color{{darkblue}} {escape_latex(main_title)} \par}}

\vspace{{0.5cm}}
{{\Large\color{{sectioncolor}} {escape_latex(subtitle)} \par}}

\vspace{{2cm}}
{{\large {escape_latex(authors)} \par}}

\vfill
{{\large \today \par}}
\end{{titlepage}}

% Acknowledgments
\chapter*{{Acknowledgments}}
\begin{{itemize}}
{ack_lines}
\end{{itemize}}

\clearpage

% Table of Contents
\tableofcontents
\clearpage
"""


def generate_references_bib():
    return r"""% Academic papers
@article{dijkstra1968,
  author  = {Dijkstra, Edsger W.},
  title   = {The Structure of the ``{THE}''-Multiprogramming System},
  journal = {Communications of the ACM},
  volume  = {11},
  number  = {5},
  pages   = {341--346},
  year    = {1968},
}

@article{popek1974,
  author  = {Popek, Gerald J. and Goldberg, Robert P.},
  title   = {Formal Requirements for Virtualizable Third Generation Architectures},
  journal = {Communications of the ACM},
  volume  = {17},
  number  = {7},
  pages   = {412--421},
  year    = {1974},
}

@article{liedtke1995,
  author  = {Liedtke, Jochen},
  title   = {On $\mu$-Kernel Construction},
  journal = {ACM SIGOPS Operating Systems Review},
  volume  = {29},
  number  = {5},
  pages   = {237--250},
  year    = {1995},
}

@inproceedings{barham2003,
  author    = {Barham, Paul and Dragovic, Boris and Fraser, Keir and Hand, Steven and Harris, Tim and Ho, Alex and Neugebauer, Rolf and Pratt, Ian and Warfield, Andrew},
  title     = {Xen and the Art of Virtualization},
  booktitle = {Proceedings of the Nineteenth ACM Symposium on Operating Systems Principles},
  pages     = {164--177},
  year      = {2003},
}

@inproceedings{kivity2007,
  author    = {Kivity, Avi and Kamay, Yaniv and Laor, Dor and Lublin, Uri and Liguori, Anthony},
  title     = {{kvm}: the {Linux} Virtual Machine Monitor},
  booktitle = {Proceedings of the Linux Symposium},
  pages     = {225--230},
  year      = {2007},
}

@inproceedings{verma2015,
  author    = {Verma, Abhishek and Pedrosa, Luis and Korupolu, Madhukar and Oppenheimer, David and Tune, Eric and Wilkes, John},
  title     = {Large-scale cluster management at {Google} with {Borg}},
  booktitle = {Proceedings of the Tenth European Conference on Computer Systems},
  pages     = {1--17},
  year      = {2015},
}

@inproceedings{brewer2000,
  author    = {Brewer, Eric A.},
  title     = {Towards Robust Distributed Systems},
  booktitle = {Proceedings of the Nineteenth Annual ACM Symposium on Principles of Distributed Computing},
  pages     = {7},
  year      = {2000},
}

@book{dobies2020,
  author    = {Dobies, Jason and Wood, Joshua},
  title     = {Kubernetes Operators: Automating the Container Orchestration Platform},
  publisher = {O'Reilly Media},
  year      = {2020},
}

% Online resources
@online{alibaba_containers,
  title   = {Introduction to Container Technology and Its Basic Principles},
  url     = {https://www.alibabacloud.com/blog/601759},
  urldate = {2024-01-01},
}

@online{fowler_microservices,
  author  = {Fowler, Martin},
  title   = {The Microservices Resource Guide},
  url     = {https://martinfowler.com/microservices/},
  urldate = {2024-01-01},
}

@online{dean2008,
  title   = {Building Software Systems at {Google} and Lessons Learned},
  note    = {Based on Jeff Dean's 2008 presentation},
  url     = {https://perspectives.mvdirona.com/2008/06/jeff-dean-on-google-infrastructure/},
  urldate = {2024-01-01},
}

@online{etcd_kubernetes,
  title   = {How etcd works with and without {Kubernetes}},
  url     = {https://learnkube.com/etcd-kubernetes},
  urldate = {2024-01-01},
}

@online{consistency_models,
  title   = {Consistency Models: Strong vs Eventual in {Kubernetes}},
  url     = {https://hokstadconsulting.com/blog/consistency-models-strong-vs-eventual-in-kubernetes},
  urldate = {2024-01-01},
}

@online{k8s_operator_pattern,
  title   = {The Operator Pattern --- {Kubernetes} Documentation},
  url     = {https://kubernetes.io/docs/concepts/extend-kubernetes/operator/},
  urldate = {2024-01-01},
}

@online{k8s_custom_resources,
  title   = {Custom Resources --- {Kubernetes} Documentation},
  url     = {https://kubernetes.io/docs/concepts/extend-kubernetes/api-extension/custom-resources/},
  urldate = {2024-01-01},
}

@online{k8s_admission_control,
  title   = {Dynamic Admission Control --- {Kubernetes} Documentation},
  url     = {https://kubernetes.io/docs/reference/access-authn-authz/extensible-admission-controllers/},
  urldate = {2024-01-01},
}

@online{helm_docs,
  title   = {Helm Documentation},
  url     = {https://helm.sh/docs/},
  urldate = {2024-01-01},
}

@online{operatorhub,
  title   = {{OperatorHub.io}},
  url     = {https://operatorhub.io/},
  urldate = {2024-01-01},
}

@online{cncf_wasm,
  title   = {{WebAssembly} ({Wasm}) on {Kubernetes}: A New Era of Cloud-Native Application Development},
  url     = {https://www.cncf.io/blog/2023/10/18/wasm-on-kubernetes-a-new-era-of-cloud-native-application-development/},
  urldate = {2024-01-01},
}

@online{datadog_ebpf,
  title   = {{eBPF} --- An Introduction and Deep Dive, with a focus on {Kubernetes}},
  url     = {https://www.datadoghq.com/blog/ebpf-101/},
  urldate = {2024-01-01},
}
"""


def generate_makefile():
    return """# Makefile for Learning Kubernetes LaTeX book
.PHONY: all clean

all: main.pdf

main.pdf: main.tex preamble.tex frontmatter.tex summary.tex ch1.tex ch2.tex ch3.tex ch4.tex ch5.tex ch6.tex conclusion.tex references.bib figures/*.tex
\tlatexmk -pdf -interaction=nonstopmode main.tex

clean:
\tlatexmk -C
\trm -f *.bbl *.run.xml *.bcf
"""


# ---------------------------------------------------------------------------
# TikZ figure definitions
# ---------------------------------------------------------------------------

def get_tikz_figures():
    """Return dict mapping figure filename (without .tex) to TikZ code."""
    figures = {}

    # ===== Figure S.1: Book Roadmap =====
    figures["figS_1"] = r"""% Figure S.1: Book roadmap
\begin{tikzpicture}[node distance=0.5cm and 0.5cm]
  \node[mnode, fill=darkblue, minimum width=2cm] (ch1)
    {\textbf{Ch 1}\\\scriptsize Building Blocks};
  \node[mnode, fill=sectioncolor, minimum width=2cm, right=of ch1] (ch2)
    {\textbf{Ch 2}\\\scriptsize Micro Revolution};
  \node[mnode, fill=oceanblue, minimum width=2cm, right=of ch2] (ch3)
    {\textbf{Ch 3}\\\scriptsize VM Takes Over};
  \node[mnode, fill=k8sred, minimum width=2cm, right=of ch3] (ch4)
    {\textbf{Ch 4}\\\scriptsize Hardware Truth};
  \node[mnode, fill=k8sgreen, minimum width=2cm, right=of ch4] (ch5)
    {\textbf{Ch 5}\\\scriptsize The Conductor};
  \node[mnode, fill=k8spurple, minimum width=2cm, right=of ch5] (ch6)
    {\textbf{Ch 6}\\\scriptsize Extensibility};
  \node[mnode, fill=k8sorange, minimum width=2cm, right=of ch6] (conc)
    {\textbf{Concl.}\\\scriptsize Future};

  \draw[arr] (ch1) -- (ch2);
  \draw[arr] (ch2) -- (ch3);
  \draw[arr] (ch3) -- (ch4);
  \draw[arr] (ch4) -- (ch5);
  \draw[arr] (ch5) -- (ch6);
  \draw[arr] (ch6) -- (conc);
\end{tikzpicture}"""

    # ===== Figure 1.1: Dijkstra Layer Stack =====
    figures["fig1_1"] = r"""% Figure 1.1: Dijkstra's THE Multiprogramming System layer stack
\begin{tikzpicture}[node distance=0.4cm, every node/.style={minimum width=6cm}]
  \node[mnode, fill=cloudgray, text=darkblue]                        (L5) {Layer 5: The Operator (User)};
  \node[mnode, fill=silvergray, text=darkblue, below=of L5]         (L4) {Layer 4: User Programs};
  \node[mnode, fill=lightgray, text=darkblue, below=of L4]          (L3) {Layer 3: I/O Buffering};
  \node[mnode, fill=k8sgray, below=of L3]                            (L2) {Layer 2: Console I/O};
  \node[mnode, fill=sectioncolor, below=of L2]                       (L1) {Layer 1: Memory Management};
  \node[mnode, fill=darkblue, below=of L1]                           (L0) {Layer 0: Processor Allocation};

  \draw[arr] (L5) -- (L4);
  \draw[arr] (L4) -- (L3);
  \draw[arr] (L3) -- (L2);
  \draw[arr] (L2) -- (L1);
  \draw[arr] (L1) -- (L0);
\end{tikzpicture}"""

    # ===== Figure 1.2: Kubernetes Interface Layers =====
    figures["fig1_2"] = r"""% Figure 1.2: Kubernetes interface layers
\begin{tikzpicture}[node distance=0.6cm and 1.2cm]
  % Core
  \node[mnode, fill=k8sblue, minimum width=3.5cm] (k8s) {Kubernetes Control Plane};

  % Interfaces
  \node[mnode, fill=oceanblue, right=2cm of k8s, yshift=1.2cm] (csi) {CSI -- Storage};
  \node[mnode, fill=oceanblue, right=2cm of k8s]               (cni) {CNI -- Networking};
  \node[mnode, fill=oceanblue, right=2cm of k8s, yshift=-1.2cm](cri) {CRI -- Runtime};

  % Implementations
  \node[mnode, fill=lightgray, text=darkblue, right=1.8cm of csi, yshift=0.6cm, minimum width=1.8cm, font=\scriptsize] (ebs)  {Amazon EBS};
  \node[mnode, fill=lightgray, text=darkblue, right=1.8cm of csi, yshift=-0.6cm, minimum width=1.8cm, font=\scriptsize] (gce)  {GCE PD};

  \node[mnode, fill=lightgray, text=darkblue, right=1.8cm of cni, yshift=0.6cm, minimum width=1.8cm, font=\scriptsize] (calico) {Calico};
  \node[mnode, fill=lightgray, text=darkblue, right=1.8cm of cni, yshift=-0.6cm, minimum width=1.8cm, font=\scriptsize] (cilium) {Cilium};

  \node[mnode, fill=lightgray, text=darkblue, right=1.8cm of cri, yshift=0.6cm, minimum width=1.8cm, font=\scriptsize] (ctrd) {containerd};
  \node[mnode, fill=lightgray, text=darkblue, right=1.8cm of cri, yshift=-0.6cm, minimum width=1.8cm, font=\scriptsize] (crio) {CRI-O};

  \draw[arr] (k8s) -- (csi);
  \draw[arr] (k8s) -- (cni);
  \draw[arr] (k8s) -- (cri);
  \draw[arr] (csi) -- (ebs);
  \draw[arr] (csi) -- (gce);
  \draw[arr] (cni) -- (calico);
  \draw[arr] (cni) -- (cilium);
  \draw[arr] (cri) -- (ctrd);
  \draw[arr] (cri) -- (crio);

  % Labels
  \node[above=0.3cm of k8s, font=\small\bfseries, color=darkblue] {Core};
  \node[above=0.3cm of cni, font=\small\bfseries, color=darkblue, yshift=1.2cm] {Standard Interfaces};
  \node[above=0.3cm of calico, font=\small\bfseries, color=darkblue, yshift=0.6cm] {Implementations};
\end{tikzpicture}"""

    # ===== Figure 1.3: Container Anatomy =====
    figures["fig1_3"] = r"""% Figure 1.3: Container anatomy
\begin{tikzpicture}[node distance=0.3cm]
  % Container A
  \node[mnode, fill=oceanblue, font=\scriptsize, minimum width=3.2cm] (pid_a) {PID Namespace (sees PID 1)};
  \node[mnode, fill=oceanblue, font=\scriptsize, minimum width=3.2cm, below=of pid_a] (mnt_a) {Mount Namespace};
  \node[mnode, fill=oceanblue, font=\scriptsize, minimum width=3.2cm, below=of mnt_a] (net_a) {Network Namespace};
  \node[mnode, fill=oceanblue, font=\scriptsize, minimum width=3.2cm, below=of net_a] (cg_a) {cgroup: 1 core, 2GB};
  \begin{scope}[on background layer]
    \node[fit=(pid_a)(cg_a), subgraph={Container A}, fill=oceanblue!8] (ca) {};
  \end{scope}

  % Container B
  \node[mnode, fill=k8sgreen, font=\scriptsize, minimum width=3.2cm, right=1.5cm of pid_a] (pid_b) {PID Namespace (sees PID 1)};
  \node[mnode, fill=k8sgreen, font=\scriptsize, minimum width=3.2cm, below=of pid_b] (mnt_b) {Mount Namespace};
  \node[mnode, fill=k8sgreen, font=\scriptsize, minimum width=3.2cm, below=of mnt_b] (net_b) {Network Namespace};
  \node[mnode, fill=k8sgreen, font=\scriptsize, minimum width=3.2cm, below=of net_b] (cg_b) {cgroup: 0.5 core, 1GB};
  \begin{scope}[on background layer]
    \node[fit=(pid_b)(cg_b), subgraph={Container B}, fill=k8sgreen!8] (cb) {};
  \end{scope}

  % Shared kernel
  \node[mnode, fill=darkblue, minimum width=8.5cm, below=1cm of $(cg_a.south)!0.5!(cg_b.south)$] (kernel) {Shared Linux Kernel};
  \begin{scope}[on background layer]
    \node[fit=(kernel), subgraph={Host Machine}, fill=darkblue!5] (host) {};
  \end{scope}

  \draw[arr] (ca.south) -- (kernel);
  \draw[arr] (cb.south) -- (kernel);
\end{tikzpicture}"""

    # ===== Figure 1.4: VM vs Container vs Kata =====
    figures["fig1_4"] = r"""% Figure 1.4: VM vs Container vs Kata Containers
\begin{tikzpicture}[node distance=0.3cm, every node/.style={minimum width=3cm, font=\scriptsize}]
  % VM Stack
  \node[mnode, fill=k8sred] (vm_app) {Application};
  \node[mnode, fill=k8sred, below=of vm_app] (vm_lib) {Libraries / Bins};
  \node[mnode, fill=k8sred, below=of vm_lib] (vm_guest) {Guest OS (full kernel)};
  \node[mnode, fill=k8sred, below=of vm_guest] (vm_hyp) {Hypervisor};
  \node[mnode, fill=k8sred, below=of vm_hyp] (vm_hw) {Hardware};
  \draw[arr] (vm_app) -- (vm_lib);
  \draw[arr] (vm_lib) -- (vm_guest);
  \draw[arr] (vm_guest) -- (vm_hyp);
  \draw[arr] (vm_hyp) -- (vm_hw);
  \node[above=0.2cm of vm_app, font=\small\bfseries, color=k8sred] {Virtual Machine};

  % Container Stack
  \node[mnode, fill=oceanblue, right=1.5cm of vm_app] (c_app) {Application};
  \node[mnode, fill=oceanblue, below=of c_app] (c_lib) {Libraries / Bins};
  \node[mnode, fill=oceanblue, below=of c_lib] (c_rt) {Container Runtime};
  \node[mnode, fill=oceanblue, below=of c_rt] (c_host) {Host OS (shared kernel)};
  \node[mnode, fill=oceanblue, below=of c_host] (c_hw) {Hardware};
  \draw[arr] (c_app) -- (c_lib);
  \draw[arr] (c_lib) -- (c_rt);
  \draw[arr] (c_rt) -- (c_host);
  \draw[arr] (c_host) -- (c_hw);
  \node[above=0.2cm of c_app, font=\small\bfseries, color=oceanblue] {Container};

  % Kata Stack
  \node[mnode, fill=k8spurple, right=1.5cm of c_app] (k_app) {Application};
  \node[mnode, fill=k8spurple, below=of k_app] (k_lib) {Libraries / Bins};
  \node[mnode, fill=k8spurple, below=of k_lib] (k_micro) {Lightweight Micro-VM};
  \node[mnode, fill=k8spurple, below=of k_micro] (k_hyp) {Hypervisor};
  \node[mnode, fill=k8spurple, below=of k_hyp] (k_host) {Host OS};
  \node[mnode, fill=k8spurple, below=of k_host] (k_hw) {Hardware};
  \draw[arr] (k_app) -- (k_lib);
  \draw[arr] (k_lib) -- (k_micro);
  \draw[arr] (k_micro) -- (k_hyp);
  \draw[arr] (k_hyp) -- (k_host);
  \draw[arr] (k_host) -- (k_hw);
  \node[above=0.2cm of k_app, font=\small\bfseries, color=k8spurple] {Kata Container};
\end{tikzpicture}"""

    # ===== Figure 2.1: Monolithic vs Microkernel =====
    figures["fig2_1"] = r"""% Figure 2.1: Monolithic kernel vs. microkernel
\begin{tikzpicture}[node distance=0.3cm]
  % --- Monolithic ---
  \node[mnode, fill=lightgray, text=darkblue, minimum width=5cm] (mk_app) {User Applications};
  \node[mnode, fill=k8sred, minimum width=5cm, below=0.5cm of mk_app] (mk_sched) {Scheduler};
  \node[mnode, fill=k8sred, minimum width=5cm, below=of mk_sched] (mk_mem) {Memory Management};
  \node[mnode, fill=k8sred, minimum width=5cm, below=of mk_mem] (mk_fs) {File System};
  \node[mnode, fill=k8sred, minimum width=5cm, below=of mk_fs] (mk_net) {Networking};
  \node[mnode, fill=k8sred, minimum width=5cm, below=of mk_net] (mk_drv) {Device Drivers};
  \begin{scope}[on background layer]
    \node[fit=(mk_sched)(mk_drv), subgraph={Kernel Space (privileged)}, fill=k8sred!8] {};
  \end{scope}
  \node[mnode, fill=k8sgray, minimum width=5cm, below=0.8cm of mk_drv] (mk_hw) {Hardware};
  \draw[arr] (mk_app) -- (mk_sched);
  \draw[arr] (mk_drv) -- (mk_hw);
  \node[above=0.3cm of mk_app, font=\small\bfseries] {Monolithic Kernel};

  % --- Microkernel ---
  \node[mnode, fill=oceanblue, minimum width=1.8cm, font=\scriptsize, right=3cm of mk_app] (mu_app) {Applications};
  \node[mnode, fill=oceanblue, minimum width=1.8cm, font=\scriptsize, right=0.3cm of mu_app] (mu_fs) {FS Server};
  \node[mnode, fill=oceanblue, minimum width=1.8cm, font=\scriptsize, right=0.3cm of mu_fs] (mu_net) {Net Server};
  \node[mnode, fill=oceanblue, minimum width=1.8cm, font=\scriptsize, right=0.3cm of mu_net] (mu_drv) {Driver};
  \begin{scope}[on background layer]
    \node[fit=(mu_app)(mu_drv), subgraph={User Space}, fill=oceanblue!8] (mu_us) {};
  \end{scope}

  \node[mnode, fill=k8sgreen, minimum width=2cm, font=\scriptsize, below=1cm of $(mu_fs.south)!0.5!(mu_net.south)$, xshift=-1.2cm] (mu_ipc) {IPC};
  \node[mnode, fill=k8sgreen, minimum width=2cm, font=\scriptsize, right=0.3cm of mu_ipc] (mu_mem) {Memory};
  \node[mnode, fill=k8sgreen, minimum width=2cm, font=\scriptsize, right=0.3cm of mu_mem] (mu_sc) {Scheduling};
  \begin{scope}[on background layer]
    \node[fit=(mu_ipc)(mu_sc), subgraph={Microkernel (minimal)}, fill=k8sgreen!8] (mu_kern) {};
  \end{scope}

  \node[mnode, fill=k8sgray, minimum width=7.8cm, below=0.8cm of mu_kern] (mu_hw) {Hardware};

  \draw[arr, <->] (mu_app) -- (mu_fs) node[midway, above, font=\tiny] {IPC};
  \draw[arr, <->] (mu_app) -- (mu_net) node[midway, above, font=\tiny] {};
  \draw[arr] (mu_us) -- (mu_kern);
  \draw[arr] (mu_kern) -- (mu_hw);
  \node[above=0.3cm of $(mu_app.north)!0.5!(mu_drv.north)$, font=\small\bfseries] {Microkernel};
\end{tikzpicture}"""

    # ===== Figure 2.2: Monolith vs Microservices =====
    figures["fig2_2"] = r"""% Figure 2.2: Monolith vs. microservices
\begin{tikzpicture}[node distance=0.4cm and 0.4cm]
  % --- Monolith ---
  \node[mnode, fill=k8sred, font=\scriptsize, minimum width=1.5cm] (m_ui)   {UI};
  \node[mnode, fill=k8sred, font=\scriptsize, minimum width=1.5cm, right=of m_ui]   (m_cat)  {Catalog};
  \node[mnode, fill=k8sred, font=\scriptsize, minimum width=1.5cm, right=of m_cat]  (m_cart) {Cart};
  \node[mnode, fill=darkred, font=\scriptsize, minimum width=1.5cm, right=of m_cart] (m_bill) {Billing \textbf{!}};
  \node[mnode, fill=k8sred, font=\scriptsize, minimum width=1.5cm, right=of m_bill] (m_rev)  {Reviews};
  \draw[thick, k8sred] (m_ui) -- (m_cat) -- (m_cart) -- (m_bill) -- (m_rev);
  \node[below=0.5cm of m_cart, font=\small\itshape, color=k8sred] {Billing crash = ENTIRE APP DOWN};
  \begin{scope}[on background layer]
    \node[fit=(m_ui)(m_rev), subgraph={Monolith Application}, fill=k8sred!5, inner sep=14pt] {};
  \end{scope}

  % --- Microservices ---
  \node[mnode, fill=k8sgreen, font=\scriptsize, minimum width=1.5cm, below=2.5cm of m_ui] (s_ui)   {UI \checkmark};
  \node[mnode, fill=k8sgreen, font=\scriptsize, minimum width=1.5cm, right=of s_ui]   (s_cat)  {Catalog \checkmark};
  \node[mnode, fill=k8sgreen, font=\scriptsize, minimum width=1.5cm, right=of s_cat]  (s_cart) {Cart \checkmark};
  \node[mnode, fill=k8sred,   font=\scriptsize, minimum width=1.5cm, right=of s_cart] (s_bill) {Billing \textbf{!}};
  \node[mnode, fill=k8sgreen, font=\scriptsize, minimum width=1.5cm, right=of s_bill] (s_rev)  {Reviews \checkmark};
  \draw[darr, k8sgreen] (s_ui) -- (s_cat);
  \draw[darr, k8sgreen] (s_ui) -- (s_cart);
  \draw[darr, k8sred]   (s_ui) -- (s_bill);
  \draw[darr, k8sgreen] (s_ui) -- (s_rev);
  \node[below=0.5cm of s_cart, font=\small\itshape, color=k8sgreen] {Billing crash = only billing affected};
  \begin{scope}[on background layer]
    \node[fit=(s_ui)(s_rev), subgraph={Microservices Application}, fill=k8sgreen!5, inner sep=14pt] {};
  \end{scope}
\end{tikzpicture}"""

    # ===== Figure 2.3: K8s as Distributed Microkernel =====
    figures["fig2_3"] = r"""% Figure 2.3: Kubernetes as a distributed microkernel
\begin{tikzpicture}[node distance=0.4cm and 0.6cm]
  % User Space - Pods
  \node[mnode, fill=oceanblue, minimum width=2.2cm] (pod1) {Web Server Pod};
  \node[mnode, fill=oceanblue, minimum width=2.2cm, right=of pod1] (pod2) {API Pod};
  \node[mnode, fill=oceanblue, minimum width=2.2cm, right=of pod2] (pod3) {DB Pod};
  \node[mnode, fill=oceanblue, minimum width=2.2cm, right=of pod3] (pod4) {Cache Pod};
  \begin{scope}[on background layer]
    \node[fit=(pod1)(pod4), subgraph={``User Space'' --- Application Pods}, fill=oceanblue!8, inner sep=14pt] (us) {};
  \end{scope}

  % Kernel Space - Control Plane
  \node[mnode, fill=darkblue, minimum width=2cm, below=1.5cm of $(pod2.south)!0.5!(pod3.south)$, xshift=-1.5cm] (api) {API Server};
  \node[mnode, fill=darkblue, minimum width=2cm, right=0.5cm of api] (sched) {Scheduler};
  \node[mnode, fill=darkblue, minimum width=2cm, below=of api] (cm) {Controller Mgr};
  \node[mnode, fill=darkblue, minimum width=2cm, below=of sched] (etcd) {etcd};
  \draw[darr] (api) -- (sched);
  \draw[darr] (api) -- (cm);
  \draw[darr] (api) -- (etcd);
  \begin{scope}[on background layer]
    \node[fit=(api)(sched)(cm)(etcd), subgraph={``Kernel Space'' --- Control Plane}, fill=darkblue!5, inner sep=14pt] (ks) {};
  \end{scope}

  % Nodes
  \node[mnode, fill=k8sgray, minimum width=2cm, below=1.5cm of cm, xshift=-0.5cm] (n1) {Node 1};
  \node[mnode, fill=k8sgray, minimum width=2cm, right=0.5cm of n1] (n2) {Node 2};
  \node[mnode, fill=k8sgray, minimum width=2cm, right=0.5cm of n2] (n3) {Node 3};
  \begin{scope}[on background layer]
    \node[fit=(n1)(n3), subgraph={Physical / Virtual Nodes}, fill=k8sgray!8, inner sep=14pt] {};
  \end{scope}

  \draw[arr] (pod1.south) -- (api);
  \draw[arr] (pod4.south) -- (api);
  \draw[arr] (ks) -- (n2);
\end{tikzpicture}"""

    # ===== Figure 3.1: Server Utilization Bar Chart =====
    figures["fig3_1"] = r"""% Figure 3.1: Server utilization (early 2000s)
\begin{tikzpicture}
  \begin{axis}[
    ybar,
    width=8cm, height=6cm,
    ylabel={Percentage of Server Resources},
    symbolic x coords={Used Capacity, Idle / Wasted},
    xtick=data,
    ymin=0, ymax=100,
    nodes near coords,
    nodes near coords align={vertical},
    bar width=1.8cm,
    title style={font=\bfseries},
    every node near coord/.append style={font=\small\bfseries},
  ]
  \addplot[fill=k8sred,   draw=k8sred!80]   coordinates {(Used Capacity, 12)};
  \addplot[fill=lightgray, draw=lightgray!80] coordinates {(Idle / Wasted, 88)};
  \end{axis}
\end{tikzpicture}"""

    # ===== Figure 3.2: Full Virtualization vs Paravirtualization =====
    figures["fig3_2"] = r"""% Figure 3.2: Full virtualization vs. paravirtualization (Xen)
\begin{tikzpicture}[node distance=0.6cm and 0.8cm]
  % Full Virtualization
  \node[mnode, fill=k8sred, minimum width=2.3cm, font=\scriptsize] (fg) {Guest OS};
  \node[mnode, fill=k8sred, minimum width=2.3cm, font=\scriptsize, right=of fg] (ft) {Trap \& Translate};
  \node[mnode, fill=k8sred, minimum width=2.3cm, font=\scriptsize, right=of ft] (fh) {Hypervisor};
  \node[mnode, fill=k8sred, minimum width=2.3cm, font=\scriptsize, right=of fh] (fhw) {Hardware};
  \draw[arr] (fg) -- node[above, font=\tiny] {privileged instr.} (ft);
  \draw[arr] (ft) -- node[above, font=\tiny] {emulated} (fh);
  \draw[arr] (fh) -- (fhw);
  \node[above=0.3cm of ft, font=\small\bfseries, color=k8sred] {Full Virtualization (slow)};

  % Paravirtualization
  \node[mnode, fill=k8sgreen, minimum width=2.8cm, font=\scriptsize, below=1.5cm of fg, xshift=1cm] (pg) {Modified Guest OS};
  \node[mnode, fill=k8sgreen, minimum width=2.8cm, font=\scriptsize, right=1.2cm of pg] (ph) {Xen Hypervisor};
  \node[mnode, fill=k8sgreen, minimum width=2.8cm, font=\scriptsize, right=1.2cm of ph] (phw) {Hardware};
  \draw[arr] (pg) -- node[above, font=\tiny] {hypercall (direct)} (ph);
  \draw[arr] (ph) -- (phw);
  \node[above=0.3cm of ph, font=\small\bfseries, color=k8sgreen] {Paravirtualization --- Xen (fast)};
\end{tikzpicture}"""

    # ===== Figure 3.3: KVM Architecture =====
    figures["fig3_3"] = r"""% Figure 3.3: KVM architecture
\begin{tikzpicture}[node distance=0.4cm and 0.5cm]
  % VMs
  \node[mnode, fill=oceanblue, minimum width=2.5cm] (vm1) {VM 1\\(Guest OS + App)};
  \node[mnode, fill=oceanblue, minimum width=2.5cm, right=of vm1] (vm2) {VM 2\\(Guest OS + App)};
  \node[mnode, fill=oceanblue, minimum width=2.5cm, right=of vm2] (vm3) {VM 3\\(Guest OS + App)};
  \begin{scope}[on background layer]
    \node[fit=(vm1)(vm3), subgraph={Virtual Machines (Linux Processes)}, fill=oceanblue!8, inner sep=14pt] (vms) {};
  \end{scope}

  % QEMU
  \node[mnode, fill=k8sgray, minimum width=8.8cm, below=1cm of vm2] (qemu) {QEMU --- I/O Emulation (User Space)};

  % Kernel
  \node[mnode, fill=darkblue, minimum width=3cm, below=0.8cm of qemu, xshift=-2cm] (kvm) {KVM Module\\CPU \& Mem Virt.};
  \node[mnode, fill=darkblue, minimum width=2cm, right=0.4cm of kvm] (sched) {Linux\\Scheduler};
  \node[mnode, fill=darkblue, minimum width=2cm, right=0.4cm of sched] (mem) {Memory\\Management};
  \begin{scope}[on background layer]
    \node[fit=(kvm)(mem), subgraph={Linux Kernel}, fill=darkblue!5, inner sep=14pt] (kern) {};
  \end{scope}

  % Hardware
  \node[mnode, fill=k8sgray, minimum width=4cm, below=1cm of kern, xshift=-1cm] (cpu) {CPU with VT-x / AMD-V};
  \node[mnode, fill=k8sgray, minimum width=3cm, right=0.4cm of cpu] (ram) {Physical RAM};
  \begin{scope}[on background layer]
    \node[fit=(cpu)(ram), subgraph={Hardware}, fill=k8sgray!8, inner sep=14pt] {};
  \end{scope}

  \draw[arr] (vms) -- (qemu);
  \draw[arr] (qemu) -- (kvm);
  \draw[thick, darkblue] (kvm) -- (sched);
  \draw[thick, darkblue] (kvm) -- (mem);
  \draw[arr] (kern) -- (cpu);
\end{tikzpicture}"""

    # ===== Figure 3.4: Virtualization Timeline =====
    figures["fig3_4"] = r"""% Figure 3.4: Virtualization to Kubernetes timeline
\begin{tikzpicture}
  \draw[very thick, darkblue] (0,0) -- (13,0);
  \foreach \x/\year/\event in {
    0/2003/Xen --- Paravirtualization,
    2.5/2006/Amazon EC2 on Xen,
    5/2007/KVM --- Linux as hypervisor,
    7.5/2013/Docker --- Containers go mainstream,
    10/2014/Kubernetes released,
    12.5/2017+/KubeVirt \& Kata Containers%
  } {
    \fill[darkblue] (\x,0) circle (3pt);
    \node[above=0.15cm, font=\scriptsize\bfseries, text=darkblue, text width=2.2cm, align=center] at (\x,0) {\year};
    \node[below=0.15cm, font=\tiny, text width=2.2cm, align=center] at (\x,0) {\event};
  }
\end{tikzpicture}"""

    # ===== Figure 4.1: Failure Statistics Bar Chart =====
    figures["fig4_1"] = r"""% Figure 4.1: Annual failures per ~1,800-server cluster
\begin{tikzpicture}
  \begin{axis}[
    ybar,
    width=10cm, height=6cm,
    ylabel={Number of Failures},
    symbolic x coords={Machine, Disk, Rack, Power},
    xtick=data,
    ymin=0, ymax=5000,
    nodes near coords,
    nodes near coords align={vertical},
    bar width=1.5cm,
    every node near coord/.append style={font=\small\bfseries},
    title={\bfseries Annual Failures per $\sim$1{,}800-Server Cluster},
  ]
  \addplot[fill=k8sorange, draw=k8sorange!80] coordinates {
    (Machine, 1000) (Disk, 4000) (Rack, 20) (Power, 1)
  };
  \end{axis}
\end{tikzpicture}"""

    # ===== Figure 4.2: Pets vs Cattle =====
    figures["fig4_2"] = r"""% Figure 4.2: Pets vs. cattle
\begin{tikzpicture}[node distance=0.5cm and 0.7cm]
  % Pets
  \node[mnode, fill=k8sred, font=\scriptsize, minimum width=2.2cm] (p1) {Named Server\\`web-01'};
  \node[mnode, fill=k8sred, font=\scriptsize, minimum width=2.2cm, right=of p1] (p2) {SSH in \&\\manual repair};
  \node[mnode, fill=k8sred, font=\scriptsize, minimum width=2.2cm, right=of p2] (p3) {Same server\\back online};
  \draw[arr] (p1) -- node[above, font=\tiny] {gets sick} (p2);
  \draw[arr] (p2) -- node[above, font=\tiny] {nursed back} (p3);
  \node[below=0.3cm of p2, font=\scriptsize\itshape, color=k8sred] {If it dies = CRISIS};
  \begin{scope}[on background layer]
    \node[fit=(p1)(p3), subgraph={Pets (Old Way)}, fill=k8sred!5, inner sep=16pt] {};
  \end{scope}

  % Cattle
  \node[mnode, fill=k8sgreen, font=\scriptsize, minimum width=2.2cm, below=2.5cm of p1] (c1) {Numbered Server\\\#4382};
  \node[mnode, fill=k8sgreen, font=\scriptsize, minimum width=2.2cm, right=of c1] (c2) {Terminate\\automatically};
  \node[mnode, fill=k8sgreen, font=\scriptsize, minimum width=2.2cm, right=of c2] (c3) {New healthy\\server spun up};
  \draw[arr] (c1) -- node[above, font=\tiny] {gets sick} (c2);
  \draw[arr] (c2) -- node[above, font=\tiny] {replaced} (c3);
  \node[below=0.3cm of c2, font=\scriptsize\itshape, color=k8sgreen] {If it dies = no big deal};
  \begin{scope}[on background layer]
    \node[fit=(c1)(c3), subgraph={Cattle (Kubernetes Way)}, fill=k8sgreen!5, inner sep=16pt] {};
  \end{scope}
\end{tikzpicture}"""

    # ===== Figure 4.3: Borg → Omega → Kubernetes =====
    figures["fig4_3"] = r"""% Figure 4.3: Evolution from Borg to Omega to Kubernetes
\begin{tikzpicture}[node distance=0.3cm and 0.3cm, every node/.style={font=\scriptsize}]
  % --- Borg ---
  \node[mnode, fill=k8sorange, minimum width=2.8cm] (bm) {BorgMaster\\(monolithic)};
  \node[mnode, fill=k8sorange, minimum width=1.3cm, below=0.5cm of bm, xshift=-0.7cm] (bs) {Scheduler};
  \node[mnode, fill=k8sorange, minimum width=1.3cm, right=0.2cm of bs] (bst) {State\\(in-memory)};
  \node[mnode, fill=k8sorange!60, minimum width=0.8cm, below=0.5cm of bs, xshift=-0.4cm] (bn1) {N};
  \node[mnode, fill=k8sorange!60, minimum width=0.8cm, right=0.15cm of bn1] (bn2) {N};
  \node[mnode, fill=k8sorange!60, minimum width=0.8cm, right=0.15cm of bn2] (bn3) {N};
  \draw[arr] (bm) -- (bs);
  \draw[arr] (bm) -- (bst);
  \draw[arr] (bs) -- (bn1);
  \draw[arr] (bs) -- (bn2);
  \draw[arr] (bs) -- (bn3);
  \begin{scope}[on background layer]
    \node[fit=(bm)(bn1)(bn3)(bst), subgraph={Borg (1st Gen)}, fill=k8sorange!5, inner sep=12pt] {};
  \end{scope}

  % --- Omega ---
  \node[mnode, fill=oceanblue, minimum width=1.4cm, right=2.5cm of bm, yshift=-0.2cm] (os1) {Sched A\\(web)};
  \node[mnode, fill=oceanblue, minimum width=1.4cm, right=0.3cm of os1] (os2) {Sched B\\(batch)};
  \node[mnode, fill=oceanblue, minimum width=3.2cm, below=0.5cm of $(os1.south)!0.5!(os2.south)$]
    (ost) {Shared State (Paxos)};
  \node[mnode, fill=oceanblue!60, minimum width=0.8cm, below=0.5cm of ost, xshift=-0.9cm] (on1) {N};
  \node[mnode, fill=oceanblue!60, minimum width=0.8cm, right=0.15cm of on1] (on2) {N};
  \node[mnode, fill=oceanblue!60, minimum width=0.8cm, right=0.15cm of on2] (on3) {N};
  \draw[arr] (os1) -- (ost);
  \draw[arr] (os2) -- (ost);
  \draw[arr] (ost) -- (on1);
  \draw[arr] (ost) -- (on2);
  \draw[arr] (ost) -- (on3);
  \begin{scope}[on background layer]
    \node[fit=(os1)(os2)(on1)(on3)(ost), subgraph={Omega (2nd Gen)}, fill=oceanblue!5, inner sep=12pt] {};
  \end{scope}

  % --- Kubernetes ---
  \node[mnode, fill=k8sgreen, minimum width=2.8cm, right=2.5cm of os1, xshift=0.5cm] (api) {API Server\\(single gateway)};
  \node[mnode, fill=k8sgreen, minimum width=1.3cm, below=0.5cm of api, xshift=-0.9cm] (ks) {Scheduler};
  \node[mnode, fill=k8sgreen, minimum width=1.3cm, right=0.2cm of ks] (kcm) {Controller\\Manager};
  \node[mnode, fill=k8sgreen, minimum width=2.8cm, below=0.4cm of $(ks.south)!0.5!(kcm.south)$]
    (etcd) {etcd (distributed KV)};
  \node[mnode, fill=k8sgreen!60, minimum width=0.8cm, below=0.5cm of etcd, xshift=-0.9cm] (kn1) {N};
  \node[mnode, fill=k8sgreen!60, minimum width=0.8cm, right=0.15cm of kn1] (kn2) {N};
  \node[mnode, fill=k8sgreen!60, minimum width=0.8cm, right=0.15cm of kn2] (kn3) {N};
  \draw[darr] (api) -- (ks);
  \draw[darr] (api) -- (kcm);
  \draw[darr] (api) -- (etcd);
  \draw[arr] (api.east) -- ++(0.6,0) node[right, font=\tiny, text=k8sgreen] {CRDs,\\Operators};
  \draw[arr] (etcd) -- (kn1);
  \draw[arr] (etcd) -- (kn2);
  \draw[arr] (etcd) -- (kn3);
  \begin{scope}[on background layer]
    \node[fit=(api)(ks)(kcm)(etcd)(kn1)(kn3), subgraph={Kubernetes (3rd Gen)}, fill=k8sgreen!5, inner sep=12pt] {};
  \end{scope}
\end{tikzpicture}"""

    # ===== Figure 5.1: Control Loop =====
    figures["fig5_1"] = r"""% Figure 5.1: The Kubernetes control loop
\begin{tikzpicture}[node distance=2cm and 2.5cm]
  \node[mnode, fill=darkblue, minimum width=2.5cm, minimum height=1.1cm] (obs) {Observe\\{\scriptsize(current state)}};
  \node[mnode, fill=darkblue, minimum width=2.5cm, minimum height=1.1cm, right=of obs] (cmp) {Compare\\{\scriptsize(current vs desired)}};
  \node[mnode, fill=darkblue, minimum width=2.5cm, minimum height=1.1cm, below=1.5cm of $(obs.south)!0.5!(cmp.south)$] (act) {Act\\{\scriptsize(close the gap)}};
  \node[mnode, fill=k8sblue, minimum width=2.5cm, above=1cm of cmp] (des) {Desired State};

  \draw[arr] (obs) -- (cmp);
  \draw[arr] (cmp) -- (act);
  \draw[arr] (act) -| (obs);
  \draw[arr] (des) -- node[right, font=\scriptsize] {input} (cmp);
\end{tikzpicture}"""

    # ===== Figure 5.2: Imperative vs Declarative =====
    figures["fig5_2"] = r"""% Figure 5.2: Edge-triggered (imperative) vs. level-triggered (declarative)
\begin{tikzpicture}[node distance=0.4cm and 0.5cm]
  % Imperative
  \node[mnode, fill=k8sred, font=\scriptsize, minimum width=2cm] (i1) {Command:\\docker run};
  \node[mnode, fill=k8sred, font=\scriptsize, minimum width=2cm, right=of i1] (i2) {Container\\running \checkmark};
  \node[mnode, fill=k8sred, font=\scriptsize, minimum width=2cm, right=of i2] (i3) {Container\\crashes \textbf{!}};
  \node[mnode, fill=k8sred, font=\scriptsize, minimum width=2cm, right=of i3] (i4) {State drifts\\No recovery};
  \draw[arr] (i1) -- (i2);
  \draw[arr] (i2) -- (i3);
  \draw[arr] (i3) -- (i4);
  \begin{scope}[on background layer]
    \node[fit=(i1)(i4), subgraph={Edge-Triggered (Imperative)}, fill=k8sred!5, inner sep=14pt] {};
  \end{scope}

  % Declarative
  \node[mnode, fill=k8sgreen, font=\scriptsize, minimum width=1.8cm, below=2.5cm of i1] (d1) {Declare:\\replicas: 3};
  \node[mnode, fill=k8sgreen, font=\scriptsize, minimum width=1.8cm, right=of d1] (d2) {3 Pods\\running \checkmark};
  \node[mnode, fill=k8sred, font=\scriptsize, minimum width=1.8cm, right=of d2] (d3) {1 Pod\\crashes \textbf{!}};
  \node[mnode, fill=warnorange, font=\scriptsize, minimum width=1.8cm, right=of d3] (d4) {Detected:\\2 vs 3};
  \node[mnode, fill=k8sgreen, font=\scriptsize, minimum width=1.8cm, right=of d4] (d5) {Auto-healed:\\3 Pods \checkmark};
  \draw[arr] (d1) -- (d2);
  \draw[arr] (d2) -- (d3);
  \draw[arr] (d3) -- (d4);
  \draw[arr] (d4) -- (d5);
  \draw[arr, k8sgreen] (d5) to[bend right=30] node[below, font=\tiny] {loop continues} (d4);
  \begin{scope}[on background layer]
    \node[fit=(d1)(d5), subgraph={Level-Triggered (Declarative / K8s)}, fill=k8sgreen!5, inner sep=14pt] {};
  \end{scope}
\end{tikzpicture}"""

    # ===== Figure 5.3: Reconciliation Loop Iterations =====
    figures["fig5_3"] = r"""% Figure 5.3: Reconciliation loop iterations
\begin{tikzpicture}[node distance=0.35cm, every node/.style={font=\scriptsize}]
  % Loop 1
  \node[mnode, fill=lightgray, text=darkblue, minimum width=2.5cm] (l1o) {Observed: 0};
  \node[mnode, fill=lightgray, text=darkblue, minimum width=2.5cm, below=of l1o] (l1d) {Desired: 3};
  \node[mnode, fill=k8sgreen, minimum width=2.5cm, below=of l1d] (l1a) {Create 3 Pods};
  \draw[arr] (l1o) -- (l1d);
  \draw[arr] (l1d) -- (l1a);
  \node[above=0.2cm of l1o, font=\small\bfseries] {Loop 1: Initial};

  % Loop 100
  \node[mnode, fill=lightgray, text=darkblue, minimum width=2.5cm, right=1.5cm of l1o] (l2o) {Observed: 2};
  \node[mnode, fill=lightgray, text=darkblue, minimum width=2.5cm, below=of l2o] (l2d) {Desired: 3};
  \node[mnode, fill=warnorange, minimum width=2.5cm, below=of l2d] (l2a) {Create 1 Pod};
  \draw[arr] (l2o) -- (l2d);
  \draw[arr] (l2d) -- (l2a);
  \node[above=0.2cm of l2o, font=\small\bfseries] {Loop 100: Crash};

  % Loop 1000
  \node[mnode, fill=lightgray, text=darkblue, minimum width=2.5cm, right=1.5cm of l2o] (l3o) {Observed: 4};
  \node[mnode, fill=lightgray, text=darkblue, minimum width=2.5cm, below=of l3o] (l3d) {Desired: 3};
  \node[mnode, fill=k8sred, minimum width=2.5cm, below=of l3d] (l3a) {Terminate 1 Pod};
  \draw[arr] (l3o) -- (l3d);
  \draw[arr] (l3d) -- (l3a);
  \node[above=0.2cm of l3o, font=\small\bfseries] {Loop 1000: Extra};
\end{tikzpicture}"""

    # ===== Figure 5.4: CAP Triangle =====
    figures["fig5_4"] = r"""% Figure 5.4: The CAP Theorem triangle
\begin{tikzpicture}
  \node[mnode, fill=k8sgreen, minimum width=3.5cm, minimum height=1.2cm] (C) at (90:3)
    {\textbf{Consistency (C)}\\{\scriptsize Every read gets the}\\{\scriptsize most recent write}};
  \node[mnode, fill=lightgray, text=white, minimum width=3.5cm, minimum height=1.2cm] (A) at (210:3)
    {\textbf{Availability (A)}\\{\scriptsize Every request gets}\\{\scriptsize a response}};
  \node[mnode, fill=k8sgreen, minimum width=3.5cm, minimum height=1.2cm] (P) at (330:3)
    {\textbf{Partition Tolerance (P)}\\{\scriptsize System works despite}\\{\scriptsize network splits}};

  \draw[very thick, k8sgreen] (C) -- (P) node[midway, right=0.3cm, font=\small\bfseries, color=k8sgreen, text width=3cm, align=center] {CP $\leftarrow$ etcd / K8s\\choose this};
  \draw[thick, gray] (C) -- (A);
  \draw[thick, gray] (A) -- (P);
\end{tikzpicture}"""

    # ===== Figure 5.5: Raft Consensus Sequence Diagram =====
    figures["fig5_5"] = r"""% Figure 5.5: Raft consensus in etcd
\begin{tikzpicture}
  % Actors
  \node[mnode, fill=darkblue, minimum width=1.8cm] (client) at (0,0) {Client};
  \node[mnode, fill=k8sgreen, minimum width=1.8cm] (leader) at (3.5,0) {etcd Leader};
  \node[mnode, fill=oceanblue, minimum width=1.8cm] (f1) at (7,0) {Follower 1};
  \node[mnode, fill=oceanblue, minimum width=1.8cm] (f2) at (10.5,0) {Follower 2};

  % Lifelines
  \draw[dashed, gray] (0,-0.5) -- (0,-8);
  \draw[dashed, gray] (3.5,-0.5) -- (3.5,-8);
  \draw[dashed, gray] (7,-0.5) -- (7,-8);
  \draw[dashed, gray] (10.5,-0.5) -- (10.5,-8);

  % Messages
  \draw[arr] (0,-1.2) -- node[above, font=\scriptsize] {Write request} (3.5,-1.2);
  \draw[arr, darkblue] (3.5,-2) -- (3.5,-2.5) node[right, font=\scriptsize] {Append to local log};
  \draw[arr] (3.5,-3) -- node[above, font=\scriptsize] {Replicate entry} (7,-3.5);
  \draw[arr] (3.5,-3) -- node[above, font=\scriptsize] {} (10.5,-3.5);
  \draw[arr, dashed, k8sgreen] (7,-4.2) -- node[above, font=\scriptsize] {ACK} (3.5,-4.7);
  \draw[arr, dashed, k8sgreen] (10.5,-4.5) -- node[above, font=\scriptsize] {ACK} (3.5,-5);

  % Quorum note
  \node[fill=k8sgreen!15, rounded corners, font=\scriptsize, inner sep=4pt] at (5.2,-5.7) {Quorum reached (2/3)};

  \draw[arr, darkblue] (3.5,-6.2) -- (3.5,-6.7) node[right, font=\scriptsize] {Commit entry};
  \draw[arr, dashed, k8sgreen] (3.5,-7.3) -- node[above, font=\scriptsize] {Write confirmed \checkmark} (0,-7.3);
\end{tikzpicture}"""

    # ===== Figure 5.6: etcd Watch and Controller Flow =====
    figures["fig5_6"] = r"""% Figure 5.6: etcd watch and controller flow
\begin{tikzpicture}
  % Actors
  \node[mnode, fill=darkblue, minimum width=1.6cm] (user) at (0,0) {User};
  \node[mnode, fill=k8sblue, minimum width=1.6cm] (api)  at (3.2,0) {API Server};
  \node[mnode, fill=k8sgreen, minimum width=1.6cm] (etcd) at (6.4,0) {etcd};
  \node[mnode, fill=k8spurple, minimum width=1.6cm] (ctrl) at (9.6,0) {Controller};

  % Lifelines
  \draw[dashed, gray] (0,-0.5) -- (0,-8);
  \draw[dashed, gray] (3.2,-0.5) -- (3.2,-8);
  \draw[dashed, gray] (6.4,-0.5) -- (6.4,-8);
  \draw[dashed, gray] (9.6,-0.5) -- (9.6,-8);

  % Messages
  \draw[arr] (0,-1.2) -- node[above, font=\scriptsize] {Apply YAML} (3.2,-1.2);
  \draw[arr] (3.2,-2) -- node[above, font=\scriptsize] {Store desired state} (6.4,-2);
  \draw[arr, dashed, k8sgreen] (6.4,-3) -- node[above, font=\scriptsize] {Watch notification} (9.6,-3);
  \draw[arr, k8spurple] (9.6,-3.8) -- (9.6,-4.3) node[right, font=\scriptsize] {Compare desired vs observed};
  \draw[arr] (9.6,-5) -- node[above, font=\scriptsize] {Take action} (3.2,-5);
  \draw[arr] (3.2,-5.8) -- node[above, font=\scriptsize] {Update state} (6.4,-5.8);

  \node[fill=k8spurple!15, rounded corners, font=\scriptsize, inner sep=4pt] at (8,-7) {Loop continues\ldots};
\end{tikzpicture}"""

    # ===== Figure 6.1: CRD Registration Flow =====
    figures["fig6_1"] = r"""% Figure 6.1: CRD registration flow
\begin{tikzpicture}
  % Actors
  \node[mnode, fill=darkblue, minimum width=1.6cm] (admin) at (0,0) {Admin};
  \node[mnode, fill=k8sblue, minimum width=1.6cm] (api) at (4,0) {API Server};
  \node[mnode, fill=k8sgreen, minimum width=1.6cm] (etcd) at (8,0) {etcd};

  % Lifelines
  \draw[dashed, gray] (0,-0.5) -- (0,-10);
  \draw[dashed, gray] (4,-0.5) -- (4,-10);
  \draw[dashed, gray] (8,-0.5) -- (8,-10);

  % Phase 1: Register CRD
  \draw[arr] (0,-1.2) -- node[above, font=\scriptsize] {Register CRD (MySQLCluster schema)} (4,-1.2);
  \draw[arr] (4,-2) -- node[above, font=\scriptsize] {Store CRD definition} (8,-2);
  \draw[arr, dashed, k8sgreen] (4,-2.8) -- node[above, font=\scriptsize] {CRD registered \checkmark} (0,-2.8);

  \node[fill=k8sblue!15, rounded corners, font=\scriptsize, inner sep=4pt] at (6,-3.8) {API Server now understands ``MySQLCluster''};

  % Phase 2: Create resource
  \draw[arr] (0,-5) -- node[above, font=\scriptsize] {Create MySQLCluster ``my-prod-db''} (4,-5);
  \draw[arr, k8sblue] (4,-5.8) -- (4,-6.3) node[right, font=\scriptsize] {Validate against CRD schema};
  \draw[arr] (4,-7) -- node[above, font=\scriptsize] {Store custom resource} (8,-7);
  \draw[arr, dashed, k8sgreen] (4,-7.8) -- node[above, font=\scriptsize] {MySQLCluster created \checkmark} (0,-7.8);

  \node[fill=k8sgreen!15, rounded corners, font=\scriptsize, inner sep=4pt] at (3,-9) {\code{kubectl get mysqlclusters} now works!};
\end{tikzpicture}"""

    # ===== Figure 6.2: Operator Reconciliation Loop =====
    figures["fig6_2"] = r"""% Figure 6.2: Operator reconciliation loop for MySQL cluster
\begin{tikzpicture}[node distance=0.5cm and 0.8cm]
  \node[mnode, fill=k8sblue, minimum width=2.5cm] (watch) {Watch Trigger:\\MySQLCluster created};
  \node[mnode, fill=darkblue, minimum width=2.5cm, below=of watch] (primary) {Create Primary\\Instance};
  \node[mnode, fill=darkblue, minimum width=2.5cm, below=of primary] (snap) {Take Data\\Snapshot};
  \node[mnode, fill=darkblue, minimum width=2.5cm, below=of snap] (r1) {Start Replica 1\\+ Sync};
  \node[mnode, fill=darkblue, minimum width=2.5cm, below=of r1] (r2) {Start Replica 2\\+ Sync};
  \node[mnode, fill=darkblue, minimum width=2.5cm, below=of r2] (backup) {Create Backup\\CronJob};
  \node[mnode, fill=k8sgreen, minimum width=2.5cm, below=of backup] (steady) {Steady State \checkmark\\(desired = observed)};

  \draw[arr] (watch) -- (primary);
  \draw[arr] (primary) -- (snap);
  \draw[arr] (snap) -- (r1);
  \draw[arr] (r1) -- (r2);
  \draw[arr] (r2) -- (backup);
  \draw[arr] (backup) -- (steady);
  \draw[arr, k8sgreen] (steady.east) -- ++(0.5,0) |- node[near start, right, font=\tiny] {monitoring} (steady.east);

  % Crash recovery
  \node[mnode, fill=k8sred, minimum width=2.5cm, right=3.5cm of r1] (crash) {Replica Crash \textbf{!}};
  \node[mnode, fill=warnorange, minimum width=2.5cm, below=of crash] (resync) {Check Lag\\Fresh Snapshot\\Resync New Pod};
  \draw[arr] (crash) -- (resync);
  \draw[arr, k8sgreen] (resync) -| (steady);
\end{tikzpicture}"""

    # ===== Figure 6.3: Admission Webhook Pipeline =====
    figures["fig6_3"] = r"""% Figure 6.3: Admission webhook pipeline
\begin{tikzpicture}[node distance=0.5cm and 0.7cm]
  \node[mnode, fill=darkblue, minimum width=2.2cm] (req) {API Request};
  \node[mnode, fill=k8spurple, minimum width=2.2cm, right=of req] (auth) {Authentication\\\& Authorization};
  \node[mnode, fill=oceanblue, minimum width=2.2cm, right=of auth] (mut) {Mutating\\Webhooks};
  \node[mnode, fill=k8sgray, minimum width=2.2cm, right=of mut] (schema) {Schema\\Validation};
  \node[mnode, fill=k8sorange, minimum width=2.2cm, right=of schema] (val) {Validating\\Webhooks};
  \node[mnode, fill=k8sgreen, minimum width=2.2cm, right=of val] (etcd) {etcd\\(stored)};

  \draw[arr] (req) -- (auth);
  \draw[arr] (auth) -- (mut);
  \draw[arr] (mut) -- (schema);
  \draw[arr] (schema) -- (val);
  \draw[arr] (val) -- (etcd);
\end{tikzpicture}"""

    # ===== Figure 6.4: Full Extensibility Stack =====
    figures["fig6_4"] = r"""% Figure 6.4: The full Kubernetes extensibility stack
\begin{tikzpicture}[node distance=0.5cm, every node/.style={minimum width=10cm}]
  \node[mnode, fill=k8spurple, minimum height=1cm] (helm)
    {Helm Charts --- Package \& distribute all of the above};
  \node[mnode, fill=k8sorange, minimum height=1cm, below=of helm] (wh)
    {Admission Webhooks --- Enforce custom rules (validate \& mutate)};
  \node[mnode, fill=k8sgreen, minimum height=1cm, below=of wh] (ops)
    {Operators (Custom Controllers) --- Encode domain knowledge};
  \node[mnode, fill=oceanblue, minimum height=1cm, below=of ops] (crds)
    {CRDs --- Teach Kubernetes new resource types};
  \node[mnode, fill=darkblue, minimum height=1cm, below=of crds] (core)
    {Kubernetes Core --- Pods, Services, Deployments, API Server, etcd};

  \draw[arr] (helm) -- (wh);
  \draw[arr] (wh) -- (ops);
  \draw[arr] (ops) -- (crds);
  \draw[arr] (crds) -- (core);
\end{tikzpicture}"""

    # ===== Figure C.1: 50-Year Timeline =====
    figures["figC_1"] = r"""% Figure C.1: 50-year timeline of ideas leading to Kubernetes
\begin{tikzpicture}
  \draw[very thick, darkblue] (0,0) -- (0,-14);

  \foreach \y/\year/\event in {
    0/1968/Dijkstra --- Layered architecture (THE system),
    -1.4/1974/Unix --- Processes \& isolation,
    -2.8/1974/Popek \& Goldberg --- VM formalization,
    -4.2/1995/Liedtke --- Microkernel philosophy (L4),
    -5.6/2003/Xen --- Paravirtualization,
    -7.0/2007/KVM --- Linux becomes a hypervisor,
    -8.4/2008/Google --- Borg \& failure-as-normal,
    -9.8/2013/Omega \& Docker --- Shared state + containers,
    -11.2/2014/Kubernetes --- Open-source orchestration,
    -12.6/2016+/CRDs \& Operators --- Extensible platform%
  } {
    \fill[darkblue] (0,\y) circle (3pt);
    \node[right=0.5cm, font=\small, text=darkblue, anchor=west] at (0,\y)
      {\textbf{\year} --- \event};
  }

  % Future
  \fill[k8sorange] (0,-14) circle (3pt);
  \node[right=0.5cm, font=\small, text=k8sorange, anchor=west] at (0,-14)
    {\textbf{Future} --- Wasm \& eBPF --- Next-gen efficiency};
\end{tikzpicture}"""

    # ===== Figure C.2: Future Kubernetes Stack =====
    figures["figC_2"] = r"""% Figure C.2: The future Kubernetes stack
\begin{tikzpicture}[node distance=0.5cm and 0.5cm]
  % Control Plane
  \node[mnode, fill=k8sblue, minimum width=2.5cm] (api) {API Server};
  \node[mnode, fill=k8sblue, minimum width=2.5cm, right=of api] (sched) {Scheduler};
  \node[mnode, fill=k8sblue, minimum width=2.5cm, right=of sched] (cm) {Controller Manager};
  \begin{scope}[on background layer]
    \node[fit=(api)(cm), subgraph={Kubernetes Control Plane}, fill=k8sblue!8, inner sep=14pt] (cp) {};
  \end{scope}

  % Workloads
  \node[mnode, fill=oceanblue, minimum width=3.5cm, below=1.5cm of api, xshift=0.5cm] (cont) {Containers\\(traditional)};
  \node[mnode, fill=k8spurple, minimum width=3.5cm, right=0.8cm of cont] (wasm) {Wasm Modules\\(microsecond startup)};
  \begin{scope}[on background layer]
    \node[fit=(cont)(wasm), subgraph={Managed Workloads}, fill=oceanblue!5, inner sep=14pt] (wl) {};
  \end{scope}

  % Kernel
  \node[mnode, fill=darkblue, minimum width=2.5cm, below=1.5cm of cont, xshift=1cm] (ebpf) {eBPF Programs};
  \node[mnode, fill=darkblue, minimum width=2cm, below=0.5cm of ebpf, xshift=-2cm] (net) {Networking\\(Cilium)};
  \node[mnode, fill=darkblue, minimum width=2cm, right=0.3cm of net] (sec) {Security\\(enforcement)};
  \node[mnode, fill=darkblue, minimum width=2cm, right=0.3cm of sec] (obs) {Observability\\(tracing)};
  \draw[arr, white] (ebpf) -- (net);
  \draw[arr, white] (ebpf) -- (sec);
  \draw[arr, white] (ebpf) -- (obs);
  \begin{scope}[on background layer]
    \node[fit=(ebpf)(net)(obs), subgraph={Linux Kernel}, fill=darkblue!5, inner sep=14pt] (kern) {};
  \end{scope}

  \draw[arr] (cp) -- (cont);
  \draw[arr] (cp) -- (wasm);
  \draw[arr] (cont.south) -- (kern.north -| cont.south);
  \draw[arr] (wasm.south) -- (kern.north -| wasm.south);
\end{tikzpicture}"""

    return figures


# ---------------------------------------------------------------------------
# File writing helper
# ---------------------------------------------------------------------------

def write_file(directory, filename, content):
    """Write content to a file."""
    path = os.path.join(directory, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  wrote {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Converting Kubernetes book to LaTeX...")

    # Create directories
    os.makedirs(FIGURES_DIR, exist_ok=True)

    # Read Summary.md for frontmatter
    summary_path = os.path.join(SCRIPT_DIR, "Summary.md")
    with open(summary_path, "r", encoding="utf-8") as f:
        summary_md = f.read()

    title, authors, acks = extract_frontmatter(summary_md)

    # Generate structural files
    write_file(OUTPUT_DIR, "preamble.tex", generate_preamble())
    write_file(OUTPUT_DIR, "main.tex", generate_main_tex())
    write_file(OUTPUT_DIR, "frontmatter.tex", generate_frontmatter(title, authors, acks))
    write_file(OUTPUT_DIR, "references.bib", generate_references_bib())
    write_file(OUTPUT_DIR, "Makefile", generate_makefile())

    # Generate summary (Introduction from Summary.md)
    summary_latex = process_summary(summary_md)
    write_file(OUTPUT_DIR, "summary.tex", summary_latex)

    # Generate expanded chapters
    for key, filename, prefix in CHAPTERS[1:]:  # skip summary
        md_path = os.path.join(SCRIPT_DIR, filename)
        with open(md_path, "r", encoding="utf-8") as f:
            md_text = f.read()

        latex = process_chapter(md_text, prefix)
        write_file(OUTPUT_DIR, f"{key}.tex", latex)

    # Write TikZ figures
    figures = get_tikz_figures()
    for figname, tikz_code in figures.items():
        write_file(FIGURES_DIR, f"{figname}.tex", tikz_code)

    print(f"\nDone! Generated {4 + len(CHAPTERS) + len(figures)} files in {OUTPUT_DIR}/")
    print("To build: cd latex && make")


if __name__ == "__main__":
    main()
