#!/usr/bin/env python3
"""Arranque compatible con INICIAR_GAMEB_STUDIO.bat. La lógica vive en studio/."""
from studio.http import main
from studio.desarmar.fondo import clean_background
from studio.desarmar.recortar import refine_cutout, _restore_title_letters
from studio.desarmar.unir import apply_title_review, unir_titulo

__all__ = ['main', 'clean_background', 'refine_cutout', '_restore_title_letters', 'apply_title_review', 'unir_titulo']

if __name__ == '__main__':
    main()
