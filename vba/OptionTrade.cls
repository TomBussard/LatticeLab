VERSION 1.0 CLASS
BEGIN
  MultiUse = -1
END
Attribute VB_Name = "OptionTrade"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Option Explicit

Public Kind As String
Public Strike As Double
Public Maturity As Double
Public American As Boolean
Public Payout As Double
Public Monitoring As String
Public FormulaTokens As String

' On definit le paiement du produit pour une valeur du sous-jacent
Public Function Payoff(ByVal spot As Double) As Double
    Select Case Kind
        Case "call": Payoff = MaxValue(spot - Strike, 0)
        Case "put": Payoff = MaxValue(Strike - spot, 0)
        Case "digital_call", "one_touch_up": If spot >= Strike Then Payoff = Payout
        Case "digital_put": If spot < Strike Then Payoff = Payout
        Case "custom"
            Payoff = EvaluateTokens(FormulaTokens, spot, Strike)
            If American Then Payoff = MaxValue(0, Payoff)
        Case Else: Err.Raise 5, , "Produit inconnu"
    End Select
End Function

' On compare la continuation avec le paiement immediat quand le contrat le permet
Public Function NodeValue(ByVal continuation As Double, ByVal spot As Double) As Double
    NodeValue = continuation
    If Kind = "one_touch_up" Then
        If spot >= Strike Then NodeValue = Payout
    ElseIf American Then
        NodeValue = MaxValue(continuation, MaxValue(0, Payoff(spot)))
    End If
End Function
