# -*- coding: utf-8 -*-
"""
Testes do CATALISADOR (catalyst.py) — as 9 regras R1..R9 + frescor/legado.
Rode com:  python3 test_catalyst.py
"""
import unittest
from catalyst import CatalystStore, normalizar_dir

CFG = {"catalyst": {"ativa": True, "stale_segundos": 900, "fail_closed": False}}


def store(**over):
    cfg = {"catalyst": {"ativa": True, "stale_segundos": 900, "fail_closed": False}}
    cfg["catalyst"].update(over)
    return CatalystStore(cfg)


class TestNormalizar(unittest.TestCase):
    def test_bull(self):
        for v in ("BULL", "up", "buy", "green", "1", "above"):
            self.assertEqual(normalizar_dir(v), "BULL")

    def test_bear(self):
        for v in ("BEAR", "down", "sell", "red", "-1", "below"):
            self.assertEqual(normalizar_dir(v), "BEAR")

    def test_neut(self):
        for v in ("NEUT", "n", "", None, "flat", "lateral"):
            self.assertEqual(normalizar_dir(v), "NEUT")


class TestRegras(unittest.TestCase):
    def _set(self, s, moeda, c5m, c15m, c1h, vwap):
        s.atualizar(moeda, {"c5m": c5m, "c15m": c15m, "c1h": c1h, "vwap": vwap})

    def test_R1_todos_neutros_bloqueia(self):
        s = store()
        self._set(s, "BTC", "NEUT", "NEUT", "NEUT", "NEUT")
        ok, det = s.checar("BTC", "buy")
        self.assertFalse(ok); self.assertEqual(det["regra"], "R1")

    def test_R8_segue_15m_favor(self):
        s = store()
        self._set(s, "BTC", "NEUT", "BULL", "NEUT", "NEUT")
        ok, det = s.checar("BTC", "buy")
        self.assertTrue(ok); self.assertEqual(det["regra"], "R8")

    def test_R8_15m_contra_bloqueia(self):
        s = store()
        self._set(s, "BTC", "NEUT", "BEAR", "NEUT", "NEUT")
        ok, det = s.checar("BTC", "buy")
        self.assertFalse(ok); self.assertEqual(det["regra"], "R8")

    def test_R5_5m_neutro_15m_1h_favor_entra(self):
        s = store()
        self._set(s, "BTC", "NEUT", "BULL", "BULL", "NEUT")
        ok, det = s.checar("BTC", "buy")
        self.assertTrue(ok); self.assertEqual(det["regra"], "R5")

    def test_R5_5m_neutro_sem_confirmacao_bloqueia(self):
        s = store()
        # 5m N, 15m FAVOR, 1h CONTRA -> não é R8 (1h decidido), cai no R5 e bloqueia
        self._set(s, "BTC", "NEUT", "BULL", "BEAR", "NEUT")
        ok, det = s.checar("BTC", "buy")
        self.assertFalse(ok); self.assertEqual(det["regra"], "R5")

    def test_R2b_5m_15m_contra_bloqueia(self):
        s = store()
        self._set(s, "BTC", "BEAR", "BEAR", "NEUT", "NEUT")
        ok, det = s.checar("BTC", "buy")
        self.assertFalse(ok); self.assertEqual(det["regra"], "R2b")

    def test_R4_tudo_alinhado_entra(self):
        s = store()
        self._set(s, "BTC", "BULL", "BULL", "BULL", "BULL")
        ok, det = s.checar("BTC", "buy")
        self.assertTrue(ok); self.assertEqual(det["regra"], "R4")

    def test_R2_5m_15m_favor_entra(self):
        s = store()
        # 5m+15m favor, 1h contra, vwap neutro -> não R4 (falta vwap/1h), cai R2
        self._set(s, "BTC", "BULL", "BULL", "BEAR", "NEUT")
        ok, det = s.checar("BTC", "buy")
        self.assertTrue(ok); self.assertEqual(det["regra"], "R2")

    def test_R6_5m_1h_favor_15m_neutro_entra(self):
        s = store()
        self._set(s, "BTC", "BULL", "NEUT", "BULL", "NEUT")
        ok, det = s.checar("BTC", "buy")
        self.assertTrue(ok); self.assertEqual(det["regra"], "R6")

    def test_R7_segue_5m_favor(self):
        s = store()
        self._set(s, "BTC", "BULL", "NEUT", "NEUT", "NEUT")
        ok, det = s.checar("BTC", "buy")
        self.assertTrue(ok); self.assertEqual(det["regra"], "R7")

    def test_R7_5m_contra_bloqueia(self):
        s = store()
        self._set(s, "BTC", "BEAR", "NEUT", "NEUT", "NEUT")
        ok, det = s.checar("BTC", "buy")
        self.assertFalse(ok); self.assertEqual(det["regra"], "R7")

    def test_R9_conflito_vwap_confirma_entra(self):
        s = store()
        # 5m BULL (favor buy), 15m N, 1h BEAR (contra) -> conflito; vwap BULL confirma
        self._set(s, "BTC", "BULL", "NEUT", "BEAR", "BULL")
        ok, det = s.checar("BTC", "buy")
        self.assertTrue(ok); self.assertEqual(det["regra"], "R9")

    def test_R9_conflito_vwap_nao_confirma_espera(self):
        s = store()
        self._set(s, "BTC", "BULL", "NEUT", "BEAR", "NEUT")
        ok, det = s.checar("BTC", "buy")
        self.assertFalse(ok); self.assertEqual(det["regra"], "R9")

    def test_R9_conflito_1h_lado_sinal_vwap_confirma(self):
        s = store()
        # sinal buy alinhado ao 1h: 5m BEAR (contra), 15m N, 1h BULL (favor) -> conflito
        self._set(s, "BTC", "BEAR", "NEUT", "BULL", "BULL")
        ok, det = s.checar("BTC", "buy")
        self.assertTrue(ok); self.assertEqual(det["regra"], "R9")

    def test_sell_espelho_R4(self):
        s = store()
        # venda totalmente alinhada (tudo BEAR + vwap BEAR)
        self._set(s, "ETH", "BEAR", "BEAR", "BEAR", "BEAR")
        ok, det = s.checar("ETH", "sell")
        self.assertTrue(ok); self.assertEqual(det["regra"], "R4")


class TestV2Regras(unittest.TestCase):
    """Regras NOVAS da V2: RANGING, pullback, timing 30s/1m e grade A/B/C."""

    def test_ranging_descarta(self):
        s = store()
        # entrada que seria R4 (tudo alinhado), mas mercado lateral -> descarta
        s.atualizar("BTC", {"c5m": "BULL", "c15m": "BULL", "c1h": "BULL",
                            "vwap": "BULL", "market": "RANGING"})
        ok, det = s.checar("BTC", "buy")
        self.assertFalse(ok); self.assertEqual(det["regra"], "RANGING")

    def test_ranging_desligado_entra(self):
        s = store(bloquear_ranging=False)
        s.atualizar("BTC", {"c5m": "BULL", "c15m": "BULL", "c1h": "BULL",
                            "vwap": "BULL", "market": "RANGING"})
        ok, det = s.checar("BTC", "buy")
        self.assertTrue(ok); self.assertEqual(det["regra"], "R4")

    def test_pullback_contra_cancela(self):
        s = store()
        # base R2 (5m+15m favor), mas pullback BEAR num sinal buy -> reversão
        s.atualizar("BTC", {"c5m": "BULL", "c15m": "BULL", "c1h": "BEAR",
                            "vwap": "NEUT", "pullback": "BEAR"})
        ok, det = s.checar("BTC", "buy")
        self.assertFalse(ok); self.assertEqual(det["regra"], "PB-contra")

    def test_pullback_favor_entra(self):
        s = store()
        # pullback BULL (retomada) a favor do buy -> passa (regra base R2)
        s.atualizar("BTC", {"c5m": "BULL", "c15m": "BULL", "c1h": "BEAR",
                            "vwap": "NEUT", "pullback": "BULL"})
        ok, det = s.checar("BTC", "buy")
        self.assertTrue(ok); self.assertEqual(det["regra"], "R2")

    def test_pullback_desligado_entra(self):
        s = store(pullback_ativo=False)
        s.atualizar("BTC", {"c5m": "BULL", "c15m": "BULL", "c1h": "BEAR",
                            "vwap": "NEUT", "pullback": "BEAR"})
        ok, det = s.checar("BTC", "buy")
        self.assertTrue(ok); self.assertEqual(det["regra"], "R2")

    def test_timing_ambos_contra_espera(self):
        s = store()
        # base R2 liberaria, mas 30s e 1m ambos CONTRA (BEAR num buy) -> timing ruim
        s.atualizar("BTC", {"c30s": "BEAR", "c1m": "BEAR",
                            "c5m": "BULL", "c15m": "BULL", "c1h": "BEAR",
                            "vwap": "NEUT"})
        ok, det = s.checar("BTC", "buy")
        self.assertFalse(ok); self.assertEqual(det["regra"], "timing")

    def test_timing_so_um_contra_entra(self):
        s = store()
        # só o 30s contra, 1m neutro -> NÃO bloqueia por timing
        s.atualizar("BTC", {"c30s": "BEAR", "c1m": "NEUT",
                            "c5m": "BULL", "c15m": "BULL", "c1h": "BEAR",
                            "vwap": "NEUT"})
        ok, det = s.checar("BTC", "buy")
        self.assertTrue(ok); self.assertEqual(det["regra"], "R2")

    def test_timing_desligado_entra(self):
        s = store(timing_rapido=False)
        s.atualizar("BTC", {"c30s": "BEAR", "c1m": "BEAR",
                            "c5m": "BULL", "c15m": "BULL", "c1h": "BEAR",
                            "vwap": "NEUT"})
        ok, det = s.checar("BTC", "buy")
        self.assertTrue(ok); self.assertEqual(det["regra"], "R2")

    def test_grade_A(self):
        s = store()
        s.atualizar("BTC", {"c5m": "BULL", "c15m": "BULL", "c1h": "BULL", "vwap": "BULL"})
        ok, det = s.checar("BTC", "buy")
        self.assertTrue(ok); self.assertEqual(det["grade"], "A")

    def test_grade_B(self):
        s = store()
        s.atualizar("BTC", {"c5m": "BULL", "c15m": "BULL", "c1h": "NEUT", "vwap": "NEUT"})
        ok, det = s.checar("BTC", "buy")
        self.assertTrue(ok); self.assertEqual(det["grade"], "B")

    def test_grade_C(self):
        s = store()
        # 5m+15m favor, 1h contra -> grade C (base R2 entra)
        s.atualizar("BTC", {"c5m": "BULL", "c15m": "BULL", "c1h": "BEAR", "vwap": "NEUT"})
        ok, det = s.checar("BTC", "buy")
        self.assertTrue(ok); self.assertEqual(det["grade"], "C")

    def test_grade_none_fora_do_arranjo(self):
        s = store()
        # 5m neutro -> não há alinhamento 5m+15m -> grade None
        s.atualizar("BTC", {"c5m": "NEUT", "c15m": "BULL", "c1h": "BULL", "vwap": "NEUT"})
        ok, det = s.checar("BTC", "buy")
        self.assertIsNone(det["grade"])

    def test_market_pullback_no_snapshot_e_atualizar(self):
        s = store()
        r = s.atualizar("BTC", {"c5m": "BULL", "market": "ranging", "pullback": "bull"})
        self.assertTrue(r["ok"])
        self.assertEqual(r["estado"]["market"], "RANGING")
        self.assertEqual(r["estado"]["pullback"], "BULL")
        snap = s.snapshot()
        self.assertTrue(snap["bloquear_ranging"])
        self.assertTrue(snap["pullback_ativo"])
        self.assertTrue(snap["timing_rapido"])


class TestFrescorLegado(unittest.TestCase):
    def test_sem_estado_legado_entra(self):
        s = store()
        ok, det = s.checar("BTC", "buy")
        self.assertTrue(ok); self.assertEqual(det["regra"], "legado")

    def test_sem_estado_fail_closed_bloqueia(self):
        s = store(fail_closed=True)
        ok, det = s.checar("BTC", "buy")
        self.assertFalse(ok); self.assertEqual(det["regra"], "legado_fail_closed")

    def test_estado_velho_legado(self):
        s = store(stale_segundos=1)
        s.atualizar("BTC", {"c5m": "BULL", "c15m": "BULL", "c1h": "BULL", "vwap": "BULL"})
        # força timestamp velho
        s._estado["BTC"]["ts"] -= 10
        ok, det = s.checar("BTC", "buy")
        self.assertTrue(ok); self.assertEqual(det["regra"], "legado")

    def test_desligado_passa(self):
        s = store(ativa=False)
        ok, det = s.checar("BTC", "buy")
        self.assertTrue(ok); self.assertEqual(det["regra"], "off")


class TestAtualizar(unittest.TestCase):
    def test_ignora_payload_sem_campos(self):
        s = store()
        r = s.atualizar("BTC", {"texto": "sinal qualquer"})
        self.assertFalse(r["ok"])

    def test_apelidos(self):
        s = store()
        r = s.atualizar("BTC", {"5m": "up", "15m": "n", "1h": "down", "vw": "up"})
        self.assertTrue(r["ok"])
        self.assertEqual(r["estado"]["c5m"], "BULL")
        self.assertEqual(r["estado"]["c1h"], "BEAR")

    def test_merge_parcial(self):
        s = store()
        s.atualizar("BTC", {"c5m": "BULL", "c15m": "BULL", "c1h": "BULL", "vwap": "BULL"})
        s.atualizar("BTC", {"vwap": "BEAR"})  # só o vwap muda
        st = s.estado_moeda("BTC")
        self.assertEqual(st["c5m"], "BULL")
        self.assertEqual(st["vwap"], "BEAR")


class TestNormalizarMoeda(unittest.TestCase):
    def test_perp_com_corretora(self):
        self.assertEqual(CatalystStore.normalizar_moeda("BITGET:BTCUSDT.P"), "BTC")

    def test_usdt_simples(self):
        self.assertEqual(CatalystStore.normalizar_moeda("ETHUSDT"), "ETH")

    def test_ja_base(self):
        self.assertEqual(CatalystStore.normalizar_moeda("SOL"), "SOL")

    def test_usdc(self):
        self.assertEqual(CatalystStore.normalizar_moeda("APTUSDC"), "APT")

    def test_minusculo(self):
        self.assertEqual(CatalystStore.normalizar_moeda("virtualusdt"), "VIRTUAL")

    def test_vazio(self):
        self.assertEqual(CatalystStore.normalizar_moeda(""), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
