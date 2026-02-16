# Makefile for Learning Kubernetes LaTeX book
.PHONY: all clean

all: main.pdf

main.pdf: main.tex preamble.tex frontmatter.tex summary.tex ch1.tex ch2.tex ch3.tex ch4.tex ch5.tex ch6.tex conclusion.tex references.bib figures/*.tex
	latexmk -pdf -interaction=nonstopmode main.tex

clean:
	latexmk -C
	rm -f *.bbl *.run.xml *.bcf
