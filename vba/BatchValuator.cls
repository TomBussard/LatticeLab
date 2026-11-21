VERSION 1.0 CLASS
BEGIN
  MultiUse = -1
END
Attribute VB_Name = "BatchValuator"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Option Explicit

Public Trades As Collection
Private cachedPrices As Collection
Private Const FirstGreekField As Long = 6

' On garde un prix par instrument dans chaque scenario commun
Public Sub Initialize(ByVal source As String)
    Dim rows() As String, row As Long, trade As Valuator
    Set Trades = New Collection
    Set cachedPrices = New Collection
    rows = Split(source, vbLf)
    For row = LBound(rows) To UBound(rows)
        Set trade = New Valuator
        trade.Initialize rows(row)
        Set trade.OwnerBatch = Me
        trade.LegIndex = Trades.Count + 1
        Trades.Add trade
    Next row
End Sub

' On memorise seulement les prix pour ne pas garder tous les arbres en memoire
Public Function ValueAt(ByVal index As Long, ByVal ds As Double, ByVal dv As Double, _
    ByVal dr As Double, ByVal elapsed As Double) As Double
    Dim key As String, cached As Collection
    key = CStr(ds) & ":" & CStr(dv) & ":" & CStr(dr) & ":" & CStr(elapsed)
    On Error Resume Next
    Set cached = cachedPrices(key)
    On Error GoTo 0
    If cached Is Nothing Then
        Set cached = CalculatePrices(ds, dv, dr, elapsed)
        cachedPrices.Add cached, key
    End If
    ValueAt = CDbl(cached(index))
End Function

' On reconstruit le pool apres chaque changement de parametres
Private Function CalculatePrices(ByVal ds As Double, ByVal dv As Double, _
    ByVal dr As Double, ByVal elapsed As Double) As Collection
    Dim pool As New Collection, number As Long, message As String
    On Error Resume Next
    Set CalculatePrices = PricesWithPool(ds, dv, dr, elapsed, pool)
    number = Err.Number
    message = Err.Description
    On Error GoTo 0
    ClearPool pool
    If number <> 0 Then Err.Raise number, , message
End Function

' On interrompt le scenario entier si une jambe ne peut pas etre calculee
Private Function PricesWithPool(ByVal ds As Double, ByVal dv As Double, ByVal dr As Double, _
    ByVal elapsed As Double, ByVal pool As Collection) As Collection
    Dim result As New Collection, trade As Valuator
    For Each trade In Trades
        result.Add trade.CalculateWithPool(ds, dv, dr, elapsed, pool)
    Next trade
    Set PricesWithPool = result
End Function

' On casse les references circulaires des noeuds avant de vider le pool
Private Sub ClearPool(ByVal pool As Collection)
    Dim lattice As Tree
    For Each lattice In pool
        lattice.ClearTree
    Next lattice
End Sub

' On transmet des lignes de texte pour conserver un pont COM simple et type
Public Function Run(ByVal greekNames As String) As String
    Dim rows() As String, row As Long, trade As Valuator
    ReDim rows(0 To Trades.Count - 1)
    For row = 0 To Trades.Count - 1
        Set trade = Trades(row + 1)
        rows(row) = TradeResult(trade, greekNames)
    Next row
    Run = Join(rows, vbLf)
End Function

' On releve les temps et les grecs effectivement demandes pour chaque jambe
Private Function TradeResult(ByVal trade As Valuator, ByVal greekNames As String) As String
    Dim fields() As String, names() As String, index As Long, started As Double
    names = Split(greekNames, ",")
    ReDim fields(0 To UBound(names) + FirstGreekField)
    started = ClockSeconds()
    fields(0) = NumberText(trade.ValueAt())
    fields(1) = NumberText(trade.BuildSeconds)
    fields(2) = NumberText(trade.PriceSeconds)
    fields(3) = NumberText(trade.Nodes)
    fields(4) = NumberText(trade.Pruned)
    For index = 0 To UBound(names)
        If Len(names(index)) > 0 Then fields(index + FirstGreekField) = SafeGreek(trade, names(index))
    Next index
    fields(5) = NumberText(Elapsed(started))
    TradeResult = Join(fields, vbTab)
End Function

' On libere aussi le lien entre chaque jambe et le portefeuille
Public Sub ClearReferences()
    Dim trade As Valuator
    For Each trade In Trades
        Set trade.OwnerBatch = Nothing
    Next trade
    Set Trades = Nothing
    Set cachedPrices = Nothing
End Sub
