"""Forma de tratamento e personalidade do assistente.

A preferência é sempre escolhida explicitamente pelo utilizador nas Definições
(«Voz e personalidade»). O assistente nunca a deduz do nome, da voz ou de outros dados.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

AddressMode = Literal["masculine", "feminine", "neutral", "custom"]
ADDRESS_MODES: tuple[str, ...] = ("masculine", "feminine", "neutral", "custom")


@dataclass(frozen=True)
class Persona:
    address: AddressMode = "neutral"
    custom: str = ""

    @classmethod
    def from_settings(cls, settings: dict[str, Any]) -> Persona:
        cfg = settings.get("persona") or {}
        mode = cfg.get("address", "neutral")
        if mode not in ADDRESS_MODES:
            mode = "neutral"
        return cls(address=mode, custom=str(cfg.get("custom") or "").strip()[:60])

    @property
    def vocative(self) -> str:
        """Forma de tratamento usada com moderação (saudações e relatórios), nunca em todas as frases."""
        if self.address == "masculine":
            return "senhor"
        if self.address == "feminine":
            return "senhora"
        if self.address == "custom" and self.custom:
            return self.custom
        return ""

    def g(self, masculine: str, feminine: str, neutral: str) -> str:
        """Escolhe a variante gramatical. «custom» usa a forma neutra (não se assume o género)."""
        if self.address == "masculine":
            return masculine
        if self.address == "feminine":
            return feminine
        return neutral

    def address_phrase(self, text: str) -> str:
        """Acrescenta o vocativo a uma frase curta: «Estou aqui, senhora.»"""
        v = self.vocative
        if not v:
            return text
        stripped = text.rstrip(".!?")
        end = text[len(stripped) :] or "."
        return f"{stripped}, {v}{end}"

    def greeting(self, configured: str = "") -> str:
        base = (configured or "Estou aqui. Em que posso ajudar?").strip()
        first, sep, rest = base.partition(". ")
        if sep:
            return f"{self.address_phrase(first + '.')} {rest}"
        return self.address_phrase(base)

    def welcome(self) -> str:
        return self.g("Bem-vindo de volta.", "Bem-vinda de volta.", "Olá de novo.")

    def report_intro(self, title: str) -> str:
        v = self.vocative
        return f"{title}, {v}." if v else f"{title}."
