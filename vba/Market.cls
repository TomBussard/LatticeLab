VERSION 1.0 CLASS
BEGIN
  MultiUse = -1
END
Attribute VB_Name = "Market"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Option Explicit

Public Spot As Double
Public Rate As Double
Public Volatility As Double
Public YieldRate As Double
Public Dividend As Double
Public DividendTime As Double

' On rassemble les donnees de marche utilisees par la construction de l arbre
Public Sub Configure(ByVal s As Double, ByVal r As Double, ByVal vol As Double, _
    ByVal q As Double, ByVal amount As Double, ByVal exTime As Double)
    If s <= 0 Or vol < 0 Or amount < 0 Then Err.Raise 5, , "Marche invalide"
    Spot = s
    Rate = r
    Volatility = vol
    YieldRate = q
    Dividend = amount
    DividendTime = exTime
End Sub
