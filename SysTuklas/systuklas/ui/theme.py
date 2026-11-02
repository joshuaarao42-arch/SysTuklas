"""Colours, fonts and small styling helpers."""
from __future__ import annotations

import os
import sys

import customtkinter as ctk

COLORS = {
    "bg": "#0D1117", "sidebar": "#111720", "card": "#161C26", "card_alt": "#1E2633", "border": "#263042",
    "text": "#E8EDF4", "muted": "#8896AB", "accent": "#3FA7FF", "accent_dark": "#1F6FB5",
    "good": "#34D399", "warn": "#FBBF24", "bad": "#F87171", "purple": "#A78BFA", "cyan": "#22D3EE", "pink": "#F472B6",
}
SEVERITY_COLORS = {"critical": COLORS["bad"], "warning": COLORS["warn"], "info": COLORS["accent"], "ok": COLORS["good"]}

if os.name == "nt":
    FONT_FAMILY = "Segoe UI"
elif sys.platform == "darwin":
    FONT_FAMILY = "Helvetica Neue"
else:
    FONT_FAMILY = "DejaVu Sans"


def font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)


def usage_color(pct: float) -> str:
    if pct >= 90:
        return COLORS["bad"]
    if pct >= 70:
        return COLORS["warn"]
    return COLORS["good"]


def score_color(score: int) -> str:
    return COLORS["good"] if score >= 75 else COLORS["warn"] if score >= 55 else COLORS["bad"]
