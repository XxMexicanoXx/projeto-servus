"""Wizard de boas-vindas: pergunta o nome do usuário no primeiro uso.

Usamos Tkinter (parte da stdlib do Python) para exibir o diálogo, evitando
adicionar dependências GUI extras. O diálogo é GUI-blocking só durante a
configuração inicial — depois do onboarding, o assistente funciona normalmente.
"""

from __future__ import annotations

import logging
from typing import Optional

from .user_profile import UserProfile, sanitize_name, save_profile

LOGGER = logging.getLogger(__name__)


def _ask_name_via_tk() -> Optional[str]:
    """Mostra um diálogo Tkinter perguntando o nome. Retorna ``None`` se o
    usuário cancelar ou se Tkinter não estiver disponível."""

    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError:
        LOGGER.warning("Tkinter indisponível — pulando diálogo gráfico.")
        return None

    result: dict[str, Optional[str]] = {"value": None}

    root = tk.Tk()
    root.title("VozAssistente — Boas-vindas")
    root.geometry("440x260")
    root.resizable(False, False)
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass

    style = ttk.Style()
    try:
        style.theme_use("vista" if "vista" in style.theme_names() else style.theme_use())
    except tk.TclError:
        pass

    container = ttk.Frame(root, padding=20)
    container.pack(fill="both", expand=True)

    title = ttk.Label(
        container,
        text="Bem-vindo(a) ao VozAssistente!",
        font=("Segoe UI", 13, "bold"),
    )
    title.pack(anchor="w")

    subtitle = ttk.Label(
        container,
        text=(
            "Pra eu poder te chamar pelo nome, como prefere ser chamado?\n"
            "(você pode mudar depois falando \"mudar meu nome para ...\")"
        ),
        font=("Segoe UI", 10),
        wraplength=400,
        justify="left",
    )
    subtitle.pack(anchor="w", pady=(8, 12))

    name_var = tk.StringVar()
    entry = ttk.Entry(container, textvariable=name_var, font=("Segoe UI", 11))
    entry.pack(fill="x")
    entry.focus_set()

    error_var = tk.StringVar()
    error_label = ttk.Label(container, textvariable=error_var, foreground="#c33")
    error_label.pack(anchor="w", pady=(4, 0))

    def on_confirm(event=None):  # noqa: ARG001
        candidate = sanitize_name(name_var.get())
        if candidate is None:
            error_var.set("Nome inválido. Use apenas letras, espaços e hífens (até 40 chars).")
            return
        result["value"] = candidate
        root.destroy()

    def on_skip():
        result["value"] = None
        root.destroy()

    btn_row = ttk.Frame(container)
    btn_row.pack(fill="x", pady=(16, 0))

    skip_btn = ttk.Button(btn_row, text="Pular por agora", command=on_skip)
    skip_btn.pack(side="left")

    confirm_btn = ttk.Button(btn_row, text="Confirmar", command=on_confirm)
    confirm_btn.pack(side="right")

    root.bind("<Return>", on_confirm)
    root.bind("<Escape>", lambda _e: on_skip())

    root.protocol("WM_DELETE_WINDOW", on_skip)

    # Centraliza
    root.update_idletasks()
    w = root.winfo_width()
    h = root.winfo_height()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    root.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")

    root.mainloop()
    return result["value"]


def run_onboarding_if_needed(profile: UserProfile) -> UserProfile:
    """Executa o wizard se o perfil ainda não foi configurado.

    Retorna o perfil (eventualmente atualizado e salvo).
    """

    if profile.has_completed_onboarding:
        return profile

    LOGGER.info("Iniciando onboarding (primeiro uso).")
    name = _ask_name_via_tk()
    profile.name = name
    profile.nickname = name
    profile.has_completed_onboarding = True
    save_profile(profile)
    if name:
        LOGGER.info("Onboarding concluído. Usuário se identificou como '%s'.", name)
    else:
        LOGGER.info("Onboarding concluído sem nome (usuário pulou).")
    return profile
