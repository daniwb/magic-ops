package game

import "testing"

// TestTicketSpecTargetPlayerDrawTwo is deliberately discriminating: reverting
// executeDrawEffect to use controller makes both final assertions fail.
func TestTicketSpecTargetPlayerDrawTwo(t *testing.T) {
	gs := NewGame("controller", "target", false)
	for i := 0; i < 2; i++ {
		gs.Players[1].Library.AddCard(NewCard("Target filler", TypeInstant, ManaCost{}, 1))
		gs.Players[0].Library.AddCard(NewCard("Controller filler", TypeInstant, ManaCost{}, 0))
	}
	source := NewCreature("TicketSpec draw source", ManaCost{}, 1, 1, 0)
	source.Owner, source.Controller = 0, 0
	gs.Battlefield.AddCard(source)
	obj := &StackObject{IsAbility: true, Text: "draw", Controller: 0, Card: source,
		EffectValue: map[string]interface{}{"amount": float64(2)},
		Targets: []Target{{IsCard: false, PlayerIdx: 1}}}
	if err := gs.ExecuteAbilityEffect(obj); err != nil { t.Fatalf("ExecuteAbilityEffect: %v", err) }
	if got := len(gs.Players[1].Hand.GetAll()); got != 2 { t.Fatalf("target drew %d, want 2", got) }
	if got := len(gs.Players[0].Hand.GetAll()); got != 0 { t.Fatalf("controller drew %d, want 0", got) }
}
