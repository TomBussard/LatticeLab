VERSION 1.0 CLASS
BEGIN
  MultiUse = -1
END
Attribute VB_Name = "Tree"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Option Explicit

Public MarketData As Market
Public Maturity As Double
Public Steps As Long
Public Branches As Long
Public Pruning As Double
Public Root As Node
Public LastTrunk As Node
Public PrunedNodes As Long
Public NodeCount As Long
Public BuildSeconds As Double
Public PriceSeconds As Double
Private Const DateTolerance As Double = 0.000000000001
Private Const StepTolerance As Double = 0.0000000001
Private Const FieldsPerNode As Long = 12
' On conserve les facteurs communs pour eviter de les recalculer a chaque noeud
Private dt As Double
Private discount As Double
Private forward As Double
Private varianceFactor As Double
Private alpha As Double
Private sqrtAlpha As Double
Private dividendStep As Long
Private noDivDown As Double
Private noDivMid As Double
Private noDivUp As Double

' On prepare les parametres communs a tous les noeuds
Public Sub Configure(ByVal market As Market, ByVal expiry As Double, ByVal count As Long, _
    ByVal mode As Long, ByVal threshold As Double)
    If expiry <= 0 Or count <= 0 Then Err.Raise 5, , "Maturite ou nombre de pas invalide"
    If mode <> 2 And mode <> 3 Then Err.Raise 5, , "Nombre de branches invalide"
    If threshold < 0 Or threshold >= 1 Then Err.Raise 5, , "Pruning invalide"
    Set MarketData = market
    Maturity = expiry
    Steps = count
    Branches = mode
    Pruning = threshold
    dt = expiry / count
    discount = Exp(-market.Rate * dt)
    forward = Exp((market.Rate - market.YieldRate) * dt)
    varianceFactor = ExpMinusOne(market.Volatility ^ 2 * dt)
    PrepareSpacing
    PrepareDividend
End Sub

' On reproduit les espacements binomial et trinomial du moteur initial
Private Sub PrepareSpacing()
    If Branches = 2 Then
        sqrtAlpha = 1 + varianceFactor / 2 + Sqr(varianceFactor * (1 + varianceFactor / 4))
        alpha = sqrtAlpha ^ 2
        noDivUp = 1 / (1 + sqrtAlpha)
        noDivDown = 1 - noDivUp
    Else
        alpha = Exp(MarketData.Volatility * Sqr(3 * dt))
        sqrtAlpha = Sqr(alpha)
        noDivDown = varianceFactor / ((1 - alpha) * (alpha ^ -2 - 1))
        noDivUp = noDivDown / alpha
        noDivMid = 1 - noDivDown - noDivUp
    End If
    If alpha <= 1 Then Err.Raise 5, , "Volatilite trop petite pour cette grille"
End Sub

' On repere le pas contenant la date de detachement
Private Sub PrepareDividend()
    Dim position As Double, nearest As Double
    dividendStep = -1
    If MarketData.Dividend = 0 Or MarketData.DividendTime > Maturity Then Exit Sub
    If MarketData.DividendTime <= 0 Then Exit Sub
    position = MarketData.DividendTime / dt
    nearest = Round(position)
    If Abs(position - nearest) < StepTolerance Then position = nearest
    dividendStep = CLng(-Int(-position)) - 1
    If dividendStep < 0 Then dividendStep = 0
End Sub

' On ajuste les deux moments au dividende fixe date
Private Sub Moments(ByVal spot As Double, ByVal step As Long, ByRef expected As Double, ByRef variance As Double)
    Dim adjusted As Double, afterDividend As Double
    expected = spot * forward
    adjusted = spot
    If step = dividendStep Then
        afterDividend = MaxValue(0, (step + 1) * dt - MarketData.DividendTime)
        expected = expected - MarketData.Dividend * Exp((MarketData.Rate - MarketData.YieldRate) * afterDividend)
        adjusted = spot - MarketData.Dividend * afterDividend / dt
    End If
    If expected <= 0 Then Err.Raise 5, , "Le dividende rend le forward negatif ou nul"
    variance = adjusted ^ 2 * forward ^ 2 * varianceFactor
End Sub

' On retrouve les probabilites avec la moyenne et la variance locales
Private Sub DividendProbabilities(ByVal expected As Double, ByVal variance As Double, ByVal middle As Double, _
    ByVal ratio As Double, ByRef down As Double, ByRef mid As Double, ByRef up As Double)
    Dim gap As Double, secondGap As Double
    gap = (expected - middle) / middle
    secondGap = variance / middle ^ 2 + gap * (expected / middle + 1)
    down = (secondGap - (ratio + 1) * gap) / ((1 - ratio) * (ratio ^ -2 - 1))
    up = (gap - (1 / ratio - 1) * down) / (ratio - 1)
    mid = 1 - down - up
End Sub

' On regroupe les branches tres peu probables quand le pruning est actif
Private Function Connect(ByVal current As Node, ByVal candidate As Node, ByVal step As Long) As Node
    Dim expected As Double, variance As Double
    Moments current.Price, step, expected, variance
    If Branches = 3 And current.ReachProbability < Pruning Then
        Set current.NextMid = candidate.Closest(expected, alpha)
        current.SetProbabilities 0, 1, 0
        PrunedNodes = PrunedNodes + 1
        Set Connect = current.NextMid
        Exit Function
    End If
    ConnectBranches current, candidate, expected, step
    If step = dividendStep Then
        ConnectDividend current, expected, variance
    Else
        current.SetProbabilities noDivDown, noDivMid, noDivUp
    End If
    Set Connect = current.NextDown
    If Branches = 3 Or step = dividendStep Then Set Connect = current.NextMid
End Function

' On relie chaque noeud aux etats de la colonne suivante
Private Sub ConnectBranches(ByVal current As Node, ByVal candidate As Node, ByVal expected As Double, ByVal step As Long)
    If Branches = 3 Or step = dividendStep Then
        Set current.NextMid = candidate.Closest(expected, alpha)
        Set current.NextUp = current.NextMid.Upper(alpha)
        Set current.NextDown = current.NextMid.Lower(alpha)
    Else
        Set current.NextUp = candidate.Closest(expected * sqrtAlpha, alpha)
        Set current.NextDown = current.NextUp.Lower(alpha)
    End If
End Sub

' On elargit les branches pour conserver des probabilites valides
Private Sub ConnectDividend(ByVal current As Node, ByVal expected As Double, ByVal variance As Double)
    Dim down As Double, mid As Double, up As Double, ratio As Double
    ratio = alpha
    DividendProbabilities expected, variance, current.NextMid.Price, ratio, down, mid, up
    Do While mid < 0 And down >= 0 And up >= 0
        Set current.NextUp = current.NextUp.Upper(alpha)
        Set current.NextDown = current.NextDown.Lower(alpha)
        ratio = ratio * alpha
        DividendProbabilities expected, variance, current.NextMid.Price, ratio, down, mid, up
    Loop
    current.SetProbabilities down, mid, up
End Sub

' On cumule les probabilites d atteindre la colonne suivante
Private Sub Propagate(ByVal current As Node)
    If Not current.NextDown Is Nothing Then
        current.NextDown.ReachProbability = current.NextDown.ReachProbability + current.ReachProbability * current.ProbaDown
    End If
    If Not current.NextMid Is Nothing Then
        current.NextMid.ReachProbability = current.NextMid.ReachProbability + current.ReachProbability * current.ProbaMid
    End If
    If Not current.NextUp Is Nothing Then
        current.NextUp.ReachProbability = current.NextUp.ReachProbability + current.ReachProbability * current.ProbaUp
    End If
End Sub

' On construit une colonne recombinante a partir du tronc
Private Function NextColumn(ByVal trunk As Node, ByVal step As Long) As Node
    Dim nextTrunk As New Node, current As Node, candidate As Node, expected As Double, variance As Double
    Moments trunk.Price, step, expected, variance
    If Branches = 2 And step <> dividendStep Then
        If step Mod 2 = 0 Then expected = expected * sqrtAlpha Else expected = expected / sqrtAlpha
    End If
    nextTrunk.Price = expected
    Set nextTrunk.Previous = trunk
    Set current = trunk.Top()
    Set candidate = nextTrunk
    Do While Not current Is Nothing
        Set candidate = Connect(current, candidate, step)
        Propagate current
        NodeCount = NodeCount + 1
        Set current = current.DownNode
    Loop
    Set NextColumn = nextTrunk
End Function

' On chronometre uniquement la construction du graphe
Public Sub Build()
    Dim step As Long, started As Double
    started = ClockSeconds()
    Set Root = New Node
    Root.Price = MarketData.Spot
    Root.ReachProbability = 1
    Set LastTrunk = Root
    For step = 0 To Steps - 1
        Set LastTrunk = NextColumn(LastTrunk, step)
    Next step
    BuildSeconds = Elapsed(started)
End Sub

' On remonte depuis le payoff terminal pour valoriser le contrat
Public Function Price(ByVal contract As OptionTrade) As Double
    Dim trunk As Node, current As Node, started As Double
    If Abs(contract.Maturity - Maturity) > DateTolerance Then Err.Raise 5, , "Maturites differentes"
    If LastTrunk Is Nothing Then Build
    started = ClockSeconds()
    Set current = LastTrunk.Top()
    Do While Not current Is Nothing
        current.OptionValue = contract.Payoff(current.Price)
        Set current = current.DownNode
    Loop
    Set trunk = LastTrunk.Previous
    Do While Not trunk Is Nothing
        PriceColumn trunk, contract
        Set trunk = trunk.Previous
    Loop
    Price = Root.OptionValue
    PriceSeconds = Elapsed(started)
End Function

' On applique l actualisation et l exercice eventuel a chaque noeud
Private Sub PriceColumn(ByVal trunk As Node, ByVal contract As OptionTrade)
    Dim current As Node, continuation As Double, shift As Double
    Set current = trunk.Top()
    Do While Not current Is Nothing
        shift = DividendShift(current)
        continuation = BranchValue(current, current.NextDown, current.ProbaDown, contract, shift)
        continuation = continuation + BranchValue(current, current.NextMid, current.ProbaMid, contract, shift)
        continuation = continuation + BranchValue(current, current.NextUp, current.ProbaUp, contract, shift)
        current.OptionValue = contract.NodeValue(continuation, current.Price)
        Set current = current.DownNode
    Loop
End Sub

' On reconstitue le niveau avant detachement pour le pont brownien
Private Function DividendShift(ByVal current As Node) As Double
    Dim expected As Double
    If Not current.NextDown Is Nothing Then expected = expected + current.ProbaDown * current.NextDown.Price
    If Not current.NextMid Is Nothing Then expected = expected + current.ProbaMid * current.NextMid.Price
    If Not current.NextUp Is Nothing Then expected = expected + current.ProbaUp * current.NextUp.Price
    DividendShift = MaxValue(0, current.Price * forward - expected)
End Function

' On approche les franchissements entre deux dates par un pont brownien
Private Function BranchValue(ByVal current As Node, ByVal child As Node, ByVal probability As Double, _
    ByVal contract As OptionTrade, ByVal shift As Double) As Double
    Dim hit As Double, endSpot As Double
    If child Is Nothing Or probability = 0 Then Exit Function
    BranchValue = probability * discount * child.OptionValue
    If contract.Kind <> "one_touch_up" Or contract.Monitoring <> "continuous" Then Exit Function
    If current.Price >= contract.Strike Then Exit Function
    endSpot = child.Price + shift
    hit = 1
    If endSpot < contract.Strike Then
        hit = Exp(-2 * Log(contract.Strike / current.Price) * Log(contract.Strike / endSpot) / (MarketData.Volatility ^ 2 * dt))
    End If
    BranchValue = probability * (hit * contract.Payout * Sqr(discount) + (1 - hit) * discount * child.OptionValue)
End Function

' On libere les references dans les deux directions du graphe
Public Sub ClearTree()
    Dim trunk As Node, previous As Node, current As Node, following As Node
    Set trunk = LastTrunk
    Do While Not trunk Is Nothing
        Set previous = trunk.Previous
        Set current = trunk.Top()
        Do While Not current Is Nothing
            Set following = current.DownNode
            current.ClearTreeLinks
            Set current = following
        Loop
        Set trunk = previous
    Loop
    Set Root = Nothing
    Set LastTrunk = Nothing
End Sub


' On attribue un identifiant a chaque noeud avant de relever ses liens
Public Function ExportNodes(ByVal contract As OptionTrade) As Double()
    Dim trunk As Node, current As Node, count As Long, step As Long, row As Long, data() As Double
    Set trunk = LastTrunk
    Do While Not trunk Is Nothing
        Set current = trunk.Top()
        Do While Not current Is Nothing
            count = count + 1
            current.ExportId = count
            Set current = current.DownNode
        Loop
        Set trunk = trunk.Previous
    Loop
    ' On parcourt ensuite les colonnes dans le meme ordre pour remplir le tableau
    ReDim data(1 To count, 1 To FieldsPerNode)
    Set trunk = LastTrunk
    For step = Steps To 0 Step -1
        Set current = trunk.Top()
        Do While Not current Is Nothing
            row = row + 1
            ExportNode data, row, step, current, contract
            Set current = current.DownNode
        Loop
        Set trunk = trunk.Previous
    Next step
    ExportNodes = data
End Function

' On conserve les valeurs et probabilites utilisees par le calcul
Private Sub ExportNode(ByRef data() As Double, ByVal row As Long, ByVal step As Long, _
    ByVal current As Node, ByVal contract As OptionTrade)
    data(row, 1) = current.ExportId
    data(row, 2) = step
    data(row, 3) = current.Price
    data(row, 4) = current.OptionValue
    data(row, 5) = current.ReachProbability
    If step < Steps And contract.American And contract.Payoff(current.Price) > 0 Then
        data(row, 6) = Abs(CDbl(Abs(current.OptionValue - contract.Payoff(current.Price)) < StepTolerance))
    End If
    data(row, 7) = NodeIdentifier(current.NextDown)
    data(row, 8) = NodeIdentifier(current.NextMid)
    data(row, 9) = NodeIdentifier(current.NextUp)
    data(row, 10) = current.ProbaDown
    data(row, 11) = current.ProbaMid
    data(row, 12) = current.ProbaUp
End Sub

' On reserve zero aux branches inexistantes
Private Function NodeIdentifier(ByVal current As Node) As Long
    If Not current Is Nothing Then NodeIdentifier = current.ExportId
End Function

' On assure aussi le nettoyage lors de la destruction de l arbre
Private Sub Class_Terminate()
    ClearTree
End Sub
