"""Jayth - aplicacion de escritorio. Ejecuta: pythonw app.py"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jayth.desktop import main

if __name__ == "__main__":
    main()
