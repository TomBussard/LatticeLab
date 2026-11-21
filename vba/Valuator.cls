VERSION 1.0 CLASS
BEGIN
  MultiUse = -1
END
Attribute VB_Name = "Valuator"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Option Explicit

Public OwnerBatch As BatchValuator
Public LegIndex As Long
Private Inputs() As String
Private Const MaturityTolerance As Double = 0.000000000001
Private Const FieldsPerNode As Long = 12
Public BuildSeconds As Double
Public PriceSeconds As Double
Public Nodes As Long
Public Pruned As Long
Public SpotBump As Double
Public VolatilityBump As Double
Public RateBump As Double
Public TimeBump As Double

' On charge les champs types transmis par le pont Excel
Public Sub Initialize(ByVal parameters As String)
    Inputs = Split(parameters, vbTab)
    If Inputs(10) = "one_touch_up" And Val(Inputs(0)) >= Val(Inputs(11)) Then Inputs(16) = "1"
    SpotBump = Val(Inputs(20))
    VolatilityBump = Val(Inputs(21))
    RateBump = Val(Inputs(22))
    TimeBump = Val(Inputs(23))
End Sub

' On retrouve le prix dans les scenarios partages du portefeuille
Public Function ValueAt(Optional ByVal spotShift As Double = 0, Optional ByVal volShift As Double = 0, _
    Optional ByVal rateShift As Double = 0, Optional ByVal elapsed As Double = 0) As Double
    ValueAt = OwnerBatch.ValueAt(LegIndex, spotShift, volShift, rateShift, elapsed)
End Function

' On decale le marche et retire les dividendes deja detaches
Private Function MakeMarket(ByVal ds As Double, ByVal dv As Double, ByVal dr As Double, ByVal elapsed As Double) As Market
    Dim market As New Market, dividend As Double, dividendTime As Double
    dividend = Val(Inputs(4))
    dividendTime = Val(Inputs(5)) - elapsed
    If dividendTime <= 0 Then dividend = 0
    market.Configure Val(Inputs(0)) + ds, Val(Inputs(1)) + dr, Val(Inputs(2)) + dv, _
        Val(Inputs(3)), dividend, dividendTime
    Set MakeMarket = market
End Function

' On conserve la meme definition du produit dans chaque scenario
Private Function MakeContract(ByVal elapsed As Double) As OptionTrade
    Dim contract As New OptionTrade
    contract.Maturity = Val(Inputs(6)) - elapsed
    contract.Kind = CStr(Inputs(10))
    contract.Strike = Val(Inputs(11))
    contract.American = CBool(Val(Inputs(12)))
    contract.Payout = Val(Inputs(13))
    contract.Monitoring = CStr(Inputs(14))
    contract.FormulaTokens = CStr(Inputs(15))
    If contract.Maturity < -MaturityTolerance Then
        Err.Raise 5, , "Le choc de temps depasse l'echeance"
    End If
    Set MakeContract = contract
End Function

' On traite directement les produits sans arbre necessaire
Private Function DirectValue(ByVal market As Market, ByVal contract As OptionTrade, ByRef value As Double) As Boolean
    DirectValue = True
    If contract.Maturity <= 0 Then
        value = contract.Payoff(market.Spot)
    ElseIf contract.Kind = "one_touch_up" And market.Spot >= contract.Strike Then
        value = contract.Payout
    ElseIf market.Volatility = 0 Then
        value = DeterministicValue(market, contract, CLng(Val(Inputs(7))))
    Else
        DirectValue = False
    End If
End Function

' On mesure separement la construction et la remontee de l arbre
Private Sub SaveMetrics(ByVal lattice As Tree)
    BuildSeconds = lattice.BuildSeconds
    PriceSeconds = lattice.PriceSeconds
    Nodes = lattice.NodeCount
    Pruned = lattice.PrunedNodes
End Sub

' On applique les memes differences finies que dans le moteur Python
Public Function Greek(ByVal name As String) As Double
    Select Case name
        Case "delta": Greek = DeltaAt(0)
        Case "gamma": Greek = (ValueAt(SpotBump) - 2 * ValueAt() + ValueAt(-SpotBump)) / SpotBump ^ 2
        Case "vega": Greek = (ValueAt(0, VolatilityBump) - ValueAt(0, -VolatilityBump)) / (2 * VolatilityBump)
        Case "rho": Greek = (ValueAt(0, 0, RateBump) - ValueAt(0, 0, -RateBump)) / (2 * RateBump)
        Case "volga": Greek = (ValueAt(0, VolatilityBump) - 2 * ValueAt() + ValueAt(0, -VolatilityBump)) / VolatilityBump ^ 2
        Case "vanna": Greek = VannaValue()
        Case "theta": Greek = ThetaValue()
        Case "charm": Greek = (-3 * DeltaAt(0) + 4 * DeltaAt(TimeBump) - DeltaAt(2 * TimeBump)) / (2 * TimeBump)
        Case "speed": Greek = SpeedValue()
        Case Else: Err.Raise 5, , "Grec inconnu"
    End Select
End Function

' On recentre la variation du spot pour une date donnee
Private Function DeltaAt(ByVal elapsed As Double) As Double
    DeltaAt = (ValueAt(SpotBump, 0, 0, elapsed) - ValueAt(-SpotBump, 0, 0, elapsed)) / (2 * SpotBump)
End Function

' On croise les bosses de spot et de volatilite
Private Function VannaValue() As Double
    Dim positive As Double, negative As Double
    positive = ValueAt(SpotBump, VolatilityBump) - ValueAt(SpotBump, -VolatilityBump)
    negative = ValueAt(-SpotBump, VolatilityBump) - ValueAt(-SpotBump, -VolatilityBump)
    VannaValue = (positive - negative) / (4 * SpotBump * VolatilityBump)
End Function

' On calcule la derivee troisieme avec quatre spots
Private Function SpeedValue() As Double
    Dim positive As Double, negative As Double
    positive = ValueAt(2 * SpotBump) - 2 * ValueAt(SpotBump)
    negative = 2 * ValueAt(-SpotBump) - ValueAt(-2 * SpotBump)
    SpeedValue = (positive + negative) / (2 * SpotBump ^ 3)
End Function

' On renvoie les noeuds reellement construits pour le graphique
Public Function ExportNodes() As Double()
    Dim lattice As New Tree, market As Market, contract As OptionTrade, price As Double
    If CBool(Val(Inputs(16))) Then
        ExportNodes = SettledNode()
        Exit Function
    End If
    Set market = MakeMarket(0, 0, 0, 0)
    Set contract = MakeContract(0)
    lattice.Configure market, contract.Maturity, CLng(Val(Inputs(7))), CLng(Val(Inputs(8))), Val(Inputs(9))
    price = lattice.Price(contract)
    ExportNodes = lattice.ExportNodes(contract)
    lattice.ClearTree
End Function

' On partage les arbres de meme maturite entre les jambes
Public Function CalculateWithPool(ByVal ds As Double, ByVal dv As Double, ByVal dr As Double, _
    ByVal elapsed As Double, ByVal pool As Collection) As Double
    Dim market As Market, contract As OptionTrade, lattice As Tree, fresh As Boolean
    If CBool(Val(Inputs(16))) Then
        CalculateWithPool = Val(Inputs(13))
        Exit Function
    End If
    Set market = MakeMarket(ds, dv, dr, elapsed)
    Set contract = MakeContract(elapsed)
    If DirectValue(market, contract, CalculateWithPool) Then Exit Function
    Set lattice = FindTree(pool, market, contract.Maturity, fresh)
    CalculateWithPool = lattice.Price(contract)
    If ds = 0 And dv = 0 And dr = 0 And elapsed = 0 Then
        SaveMetrics lattice
        If Not fresh Then BuildSeconds = 0
    End If
End Function

' On cree chaque arbre une seule fois pour un scenario de marche
Private Function FindTree(ByVal pool As Collection, ByVal market As Market, _
    ByVal expiry As Double, ByRef fresh As Boolean) As Tree
    Dim lattice As Tree, key As String
    key = CStr(expiry)
    On Error Resume Next
    Set lattice = pool(key)
    On Error GoTo 0
    If lattice Is Nothing Then
        fresh = True
        Set lattice = New Tree
        lattice.Configure market, expiry, CLng(Val(Inputs(7))), CLng(Val(Inputs(8))), Val(Inputs(9))
        pool.Add lattice, key
    End If
    Set FindTree = lattice
End Function

' On limite le contrat deja paye a sa racine sans trajectoire future
Private Function SettledNode() As Double()
    Dim result() As Double
    ReDim result(1 To 1, 1 To FieldsPerNode)
    result(1, 1) = 1
    result(1, 3) = Val(Inputs(0))
    result(1, 4) = Val(Inputs(13))
    result(1, 5) = 1
    SettledNode = result
End Function

' On deplace la date dans le futur en conservant les dates du contrat
Private Function ThetaValue() As Double
    Dim future As Double
    future = 4 * ValueAt(0, 0, 0, TimeBump) - ValueAt(0, 0, 0, 2 * TimeBump)
    ThetaValue = (-3 * ValueAt() + future) / (2 * TimeBump)
End Function
