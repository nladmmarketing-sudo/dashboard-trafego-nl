"""Formatação pt-BR: moeda, percentual e números compactos."""


def brl(v, casas: int = 0) -> str:
    """1234567.8 → 'R$ 1.234.568' (ou com casas decimais)."""
    if v is None:
        return "—"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    s = f"{v:,.{casas}f}".replace(",", "\0").replace(".", ",").replace("\0", ".")
    return f"R$ {s}"


def brl_compacto(v) -> str:
    """1954582 → 'R$ 1,95 mi' · 45300 → 'R$ 45,3 mil'."""
    if v is None:
        return "—"
    v = float(v)
    if abs(v) >= 1_000_000:
        return f"R$ {v / 1_000_000:.1f} mi".replace(".", ",")
    if abs(v) >= 10_000:
        return f"R$ {v / 1_000:.1f} mil".replace(".", ",")
    return brl(v)


def pct(v, casas: int = 1) -> str:
    """0.0345 → '3,5%' (recebe fração)."""
    if v is None:
        return "—"
    return f"{v * 100:.{casas}f}%".replace(".", ",")


def num(v) -> str:
    """12345 → '12.345'."""
    if v is None:
        return "—"
    return f"{int(round(float(v))):,}".replace(",", ".")


def num_compacto(v) -> str:
    """1142365 → '1,1 mi' · 733118 → '733 mil' · 9690 → '9.690'."""
    if v is None:
        return "—"
    v = float(v)
    if abs(v) >= 1_000_000:
        return f"{v / 1_000_000:.1f} mi".replace(".", ",")
    if abs(v) >= 10_000:
        return f"{v / 1_000:.0f} mil"
    return num(v)


def delta_pct(atual, anterior) -> str | None:
    """Variação percentual pronta para st.metric (None se não calculável)."""
    if anterior in (None, 0) or atual is None:
        return None
    d = (float(atual) - float(anterior)) / abs(float(anterior))
    return f"{d * 100:+.1f}%".replace(".", ",")


def nome_abreviado(nome: str | None) -> str:
    """'Maria da Silva Souza' → 'Maria S.' (LGPD: não expor nome completo)."""
    if not nome or not str(nome).strip():
        return "—"
    partes = [p for p in str(nome).split() if p]
    if len(partes) == 1:
        return partes[0]
    return f"{partes[0]} {partes[-1][0]}."
