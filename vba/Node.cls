VERSION 1.0 CLASS
BEGIN
  MultiUse = -1
END
Attribute VB_Name = "Node"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Option Explicit

' On conserve les liens du graphe et les probabilites portees par chaque noeud
Public ExportId As Long
Public Price As Double
Public OptionValue As Double
Public ReachProbability As Double
Public NextUp As Node
Public NextMid As Node
Public NextDown As Node
Public UpNode As Node
Public DownNode As Node
Public Previous As Node
Public ProbaDown As Double
Public ProbaMid As Double
Public ProbaUp As Double

' On cree le voisin superieur seulement si ce noeud manque encore
Public Function Upper(ByVal alpha As Double) As Node
    If UpNode Is Nothing Then
        Set UpNode = New Node
        UpNode.Price = Price * alpha
        Set UpNode.DownNode = Me
    End If
    Set Upper = UpNode
End Function

' On cree le voisin inferieur avec le meme espacement multiplicatif
Public Function Lower(ByVal alpha As Double) As Node
    If DownNode Is Nothing Then
        Set DownNode = New Node
        DownNode.Price = Price / alpha
        Set DownNode.UpNode = Me
    End If
    Set Lower = DownNode
End Function

' On cherche le noeud dont la zone centrale contient la cible
Public Function Closest(ByVal target As Double, ByVal alpha As Double) As Node
    Dim current As Node
    Set current = Me
    Do While target > current.Price * (1 + alpha) / 2
        Set current = current.Upper(alpha)
    Loop
    Do While target < current.Price * (1 + 1 / alpha) / 2
        Set current = current.Lower(alpha)
    Loop
    Set Closest = current
End Function

' On remonte les voisins pour parcourir une couche depuis son sommet
Public Function Top() As Node
    Dim current As Node
    Set current = Me
    Do While Not current.UpNode Is Nothing
        Set current = current.UpNode
    Loop
    Set Top = current
End Function

' On controle les probabilites avant de les utiliser pour actualiser
Public Sub SetProbabilities(ByVal down As Double, ByVal middle As Double, ByVal up As Double)
    If down < 0 Or down > 1 Or middle < 0 Or middle > 1 Or up < 0 Or up > 1 Then
        Err.Raise 5, , "Probabilite invalide pour la grille"
    End If
    If Abs(down + middle + up - 1) > 0.000000000001 Then Err.Raise 5, , "Somme des probabilites invalide"
    ProbaDown = down
    ProbaMid = middle
    ProbaUp = up
End Sub

' On libere les liens entre noeuds pour couper les references circulaires
Public Sub ClearTreeLinks()
    Set NextDown = Nothing
    Set NextMid = Nothing
    Set NextUp = Nothing
    Set DownNode = Nothing
    Set UpNode = Nothing
    Set Previous = Nothing
End Sub
