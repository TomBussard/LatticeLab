Attribute VB_Name = "Maths"
Option Explicit

Private Const SecondsPerDay As Double = 86400

#If Mac Then
#Else
' On lit le compteur haute precision pour chronometrer les calculs
Private Declare PtrSafe Function QueryPerformanceCounter Lib "kernel32" (ByRef value As Currency) As Long
' On lit la frequence du compteur pour convertir sa valeur en secondes
Private Declare PtrSafe Function QueryPerformanceFrequency Lib "kernel32" (ByRef value As Currency) As Long
#End If

' On mesure une duree precise sous Windows et on garde Timer pour le code Mac
Public Function ClockSeconds() As Double
    #If Mac Then
    ClockSeconds = Timer
    #Else
    Dim counter As Currency, frequency As Currency
    QueryPerformanceCounter counter
    QueryPerformanceFrequency frequency
    ClockSeconds = counter / frequency
    #End If
End Function

' On corrige le passage de minuit lorsque le compteur revient a zero
Public Function Elapsed(ByVal started As Double) As Double
    Elapsed = ClockSeconds() - started
    If Elapsed < 0 Then Elapsed = Elapsed + SecondsPerDay
End Function

' On renvoie la plus grande des deux valeurs
Public Function MaxValue(ByVal first As Double, ByVal second As Double) As Double
    MaxValue = first
    If second > first Then MaxValue = second
End Function

' On renvoie la plus petite des deux valeurs
Public Function MinValue(ByVal first As Double, ByVal second As Double) As Double
    MinValue = first
    If second < first Then MinValue = second
End Function

' On calcule Exp(value) moins un en preservant la precision pour les petites valeurs
Public Function ExpMinusOne(ByVal value As Double) As Double
    If Abs(value) < 0.00001 Then
        ExpMinusOne = value * (1 + value * (0.5 + value * (1 / 6 + value / 24)))
    Else
        ExpMinusOne = Exp(value) - 1
    End If
End Function

' On traduit les operations binaires autorisees dans les formules
Public Function BinaryValue(ByVal operator As String, ByVal a As Double, ByVal b As Double) As Double
    Select Case operator
        Case "+": BinaryValue = a + b
        Case "-": BinaryValue = a - b
        Case "*": BinaryValue = a * b
        Case "/": BinaryValue = a / b
        Case "**": BinaryValue = a ^ b
        Case "max": BinaryValue = MaxValue(a, b)
        Case "min": BinaryValue = MinValue(a, b)
        Case ">": BinaryValue = Abs(CDbl(a > b))
        Case ">=": BinaryValue = Abs(CDbl(a >= b))
        Case "<": BinaryValue = Abs(CDbl(a < b))
        Case "<=": BinaryValue = Abs(CDbl(a <= b))
        Case "==": BinaryValue = Abs(CDbl(a = b))
        Case "!=": BinaryValue = Abs(CDbl(a <> b))
        Case "and": BinaryValue = Abs(CDbl(a <> 0 And b <> 0))
        Case "or": BinaryValue = Abs(CDbl(a <> 0 Or b <> 0))
        Case Else: Err.Raise 5, , "Operateur de formule inconnu"
    End Select
End Function

' On limite les fonctions mathematiques aux operations prevues
Public Function UnaryValue(ByVal operator As String, ByVal value As Double) As Double
    Select Case operator
        Case "neg": UnaryValue = -value
        Case "abs": UnaryValue = Abs(value)
        Case "sqrt": UnaryValue = Sqr(value)
        Case "exp": UnaryValue = Exp(value)
        Case "log": UnaryValue = Log(value)
        Case Else: Err.Raise 5, , "Fonction de formule inconnue"
    End Select
End Function

' On evalue les jetons avec une pile et des sauts pour les conditions
Public Function EvaluateTokens(ByVal formula As String, ByVal spot As Double, ByVal strike As Double) As Double
    Dim tokens() As String, stack() As Double, depth As Long, i As Long, token As String
    tokens = Split(formula, " ")
    ReDim stack(0 To UBound(tokens) + 1)
    Do While i <= UBound(tokens)
        token = tokens(i)
        If Left$(token, 3) = "jf=" Then
            If stack(depth) = 0 Then i = CLng(Mid$(token, 4)) - 1
            depth = depth - 1
        ElseIf Left$(token, 4) = "jmp=" Then
            i = CLng(Mid$(token, 5)) - 1
        ElseIf token = "S" Or token = "K" Or Left$(token, 1) = "#" Then
            depth = depth + 1
            stack(depth) = TokenNumber(token, spot, strike)
        Else
            ApplyToken token, stack, depth
        End If
        i = i + 1
    Loop
    If depth <> 1 Then Err.Raise 5, , "Formule invalide"
    EvaluateTokens = stack(1)
End Function

' On lit seulement un nombre ou une des deux variables du payoff
Private Function TokenNumber(ByVal token As String, ByVal spot As Double, ByVal strike As Double) As Double
    Select Case token
        Case "S": TokenNumber = spot
        Case "K": TokenNumber = strike
        Case Else: TokenNumber = Val(Mid$(token, 2))
    End Select
End Function

' On verifie la pile avant de consommer les arguments de chaque operation
Private Sub ApplyToken(ByVal token As String, ByRef stack() As Double, ByRef depth As Long)
    If token = "neg" Or token = "abs" Or token = "sqrt" Or token = "exp" Or token = "log" Then
        If depth < 1 Then Err.Raise 5, , "Formule incomplete"
        stack(depth) = UnaryValue(token, stack(depth))
    ElseIf token = "if" Then
        If depth < 3 Then Err.Raise 5, , "Condition incomplete"
        If stack(depth - 2) <> 0 Then stack(depth) = stack(depth - 1)
        stack(depth - 2) = stack(depth)
        depth = depth - 2
    Else
        If depth < 2 Then Err.Raise 5, , "Formule incomplete"
        stack(depth - 1) = BinaryValue(token, stack(depth - 1), stack(depth))
        depth = depth - 1
    End If
End Sub
