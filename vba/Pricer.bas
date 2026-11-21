Attribute VB_Name = "Pricer"
Option Explicit

Private Const ErrorPrefix As String = "error:"

' On identifie le protocole de transport du classeur
Public Function Version() As String
    Version = "atelier-pricer-v3"
End Function

' On utilise le point decimal independamment de la langue d Excel
Public Function NumberText(ByVal value As Double) As String
    NumberText = Trim$(Str$(value))
End Function

' On signale chaque grec impossible sans cacher un echec de pricing
Public Function SafeGreek(ByVal valuation As Valuator, ByVal name As String) As String
    On Error Resume Next
    SafeGreek = NumberText(valuation.Greek(name))
    If Err.Number <> 0 Then SafeGreek = ErrorPrefix & Err.Description
    On Error GoTo 0
End Function

' On traite aussi la trajectoire deterministe quand la volatilite est nulle
Public Function DeterministicValue(ByVal market As Market, ByVal contract As OptionTrade, ByVal steps As Long) As Double
    Dim step As Long, time As Double, spot As Double, value As Double, best As Double
    For step = 0 To steps
        time = contract.Maturity * step / steps
        spot = market.Spot * Exp((market.Rate - market.YieldRate) * time)
        If market.Dividend > 0 And time >= market.DividendTime Then
            spot = MaxValue(0, spot - market.Dividend * Exp((market.Rate - market.YieldRate) * (time - market.DividendTime)))
        End If
        value = contract.Payoff(spot) * Exp(-market.Rate * time)
        If contract.Kind = "one_touch_up" And spot >= contract.Strike Then
            DeterministicValue = value
            Exit Function
        End If
        If contract.American And value > best Then best = value
    Next step
    DeterministicValue = value
    If contract.American Then DeterministicValue = best
End Function

' On permet d utiliser le classeur directement sans lancer le site web
Public Sub RunWorkbook()
    WorkbookUI.SaisirOption
End Sub

' On exporte un tableau numerique issu des vrais objets de l arbre
Public Function ExportTree(ByVal parameters As String) As Double()
    Dim valuation As New Valuator
    valuation.Initialize parameters
    ExportTree = valuation.ExportNodes()
End Function

' On garantit la liberation du portefeuille meme si un calcul echoue
Public Function RunBatch(ByVal rows As String, ByVal greekNames As String) As String
    Dim batch As New BatchValuator, number As Long, message As String
    On Error Resume Next
    batch.Initialize rows
    If Err.Number = 0 Then RunBatch = batch.Run(greekNames)
    number = Err.Number
    message = Err.Description
    On Error GoTo 0
    batch.ClearReferences
    If number <> 0 Then RunBatch = ErrorPrefix & message
End Function

' On transmet les erreurs d exploration sans ouvrir de boite modale Excel
Public Function ExportTreeText(ByVal parameters As String) As String
    Dim nodes() As Double, number As Long, message As String
    On Error Resume Next
    nodes = ExportTree(parameters)
    number = Err.Number
    message = Err.Description
    On Error GoTo 0
    If number <> 0 Then
        ExportTreeText = ErrorPrefix & message
    Else
        ExportTreeText = EncodeNodes(nodes)
    End If
End Function

' On conserve toutes les colonnes numeriques dans un transport texte type
Private Function EncodeNodes(ByRef nodes() As Double) As String
    Dim rows() As String, fields() As String, row As Long, field As Long
    ReDim rows(LBound(nodes, 1) To UBound(nodes, 1))
    ReDim fields(LBound(nodes, 2) To UBound(nodes, 2))
    For row = LBound(rows) To UBound(rows)
        For field = LBound(fields) To UBound(fields)
            fields(field) = NumberText(nodes(row, field))
        Next field
        rows(row) = Join(fields, vbTab)
    Next row
    EncodeNodes = Join(rows, vbLf)
End Function
