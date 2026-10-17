"""상대가 전체 solver 트리를 모르고, 한 축(hero의 fold frequency)에서만 최적 대응하는 경우의
best-response EV를 닫힌 형태로 계산. TexasSolver는 커스텀 전략에 대한 best-response를 CLI로
노출하지 않아서 전체 트리 best-response 엔진 대신, poker
이론의 "지분 분기점(indifference point)" 공식을 직접 쓴다 — bluff-catch 스팟의 교과서적 결과.

핵심 아이디어: 상대가 pot P에 bet B를 넣었을 때, hero가 폴드율 f로 수비하면 상대의 블러프 EV는
    bluff_ev(f) = f*P - (1-f)*B
GTO는 상대가 블러프와 밸류를 섞어도 무차별하도록 f_gto = B/(P+B)로 만든다. hero가 f_gto보다
더 접으면(over-fold) 상대는 그냥 100% 블러프로 전환해 bluff_ev(f)>0을 챙긴다 — 이게 실제
best-response EV. f_gto 근처에서 이 손실은 **거리에 선형**이다(코너 솔루션이라 2차가 아님).

적용 범위: hero의 fold frequency 쪽 deviation만 다룬다. raise(블러프레이즈) 빈도 deviation의
EV loss는 상대가 그 레이즈에 어떻게 반응하는지(콜/폴드)에 좌우되는 대칭적인 계산이 더 필요함 —
ponytail: 다음 단계.
"""


def gto_fold_rate(pot_bb, bet_bb):
    """상대를 블러프에 무차별하게 만드는 균형 폴드율."""
    return bet_bb / (pot_bb + bet_bb)


def best_response_bluff_ev(pot_bb, bet_bb, fold_rate):
    """hero가 fold_rate로 수비할 때, 상대가 전부 블러프로 돌려서 얻을 수 있는 EV(bb). 음수면 0."""
    return max(0.0, fold_rate * pot_bb - (1 - fold_rate) * bet_bb)


def ev_loss_from_overfolding(pot_bb, bet_bb, fold_rate):
    """GTO 폴드율 대비 실제 폴드율에서 상대가 뽑아낼 수 있는 추가 EV(bb)."""
    return best_response_bluff_ev(pot_bb, bet_bb, fold_rate) - best_response_bluff_ev(
        pot_bb, bet_bb, gto_fold_rate(pot_bb, bet_bb)
    )


def local_sensitivity(pot_bb, bet_bb):
    """f_gto 근처에서 ev_loss는 deviation 거리에 선형: ev_loss ≈ sensitivity * |f - f_gto|."""
    return pot_bb + bet_bb


def demo():
    pot, bet = 10.0, 10.0  # pot-size bet
    f_gto = gto_fold_rate(pot, bet)
    assert abs(f_gto - 0.5) < 1e-9, f_gto  # pot-size bet의 교과서 균형 폴드율 = 50%

    # 균형에서는 블러프해도 EV 0 (무차별) → EV loss 0
    assert abs(ev_loss_from_overfolding(pot, bet, f_gto)) < 1e-9

    # 균형보다 10%p 더 접으면(f=0.6), 상대가 전부 블러프 전환 → 실제 EV loss 발생
    loss = ev_loss_from_overfolding(pot, bet, 0.6)
    assert loss > 0

    # 근처에서는 선형: 거리 2배면 손실도 거의 2배 (코너 솔루션 쪽에서 약간 벗어나지 않는 한)
    loss_2x = ev_loss_from_overfolding(pot, bet, 0.7)
    assert abs(loss_2x / loss - 2.0) < 1e-9

    # local_sensitivity와 일치: loss ≈ sensitivity * deviation
    sens = local_sensitivity(pot, bet)
    assert abs(loss - sens * 0.1) < 1e-9

    print(f"ok: f_gto={f_gto}, sensitivity={sens} bb per 1.0 폴드율 deviation, loss@0.6={loss:.3f}bb")


if __name__ == "__main__":
    demo()
