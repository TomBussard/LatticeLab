VERSION 5.00
Begin {C62A69F0-16DC-11CE-9E98-00AA00574A4F} UserForm1 
   Caption         =   "UserForm1"
   ClientHeight    =   3036
   ClientLeft      =   108
   ClientTop       =   456
   ClientWidth     =   4584
   OleObjectBlob   =   "UserForm1.frx":0000
   StartUpPosition =   1  'CenterOwner
End
Attribute VB_Name = "UserForm1"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False

Option Explicit

Private WithEvents calculateButton As MSForms.CommandButton
Private WithEvents cancelButton As MSForms.CommandButton

' On crée les champs à l'ouverture du formulaire
Private Sub UserForm_Initialize()
    WorkbookUI.BuildForm Me
    Set calculateButton = Me.Controls("calculate")
    Set cancelButton = Me.Controls("cancel")
    calculateButton.Default = True
    cancelButton.Cancel = True
End Sub

' On laisse le formulaire ouvert si une saisie ou un calcul échoue
Private Sub calculateButton_Click()
    Dim number As Long, message As String
    calculateButton.Enabled = False
    Me.Controls("message").Caption = "Calcul en cours…"
    Me.Repaint
    On Error Resume Next
    WorkbookUI.ComputeForm Me
    number = Err.Number
    message = Err.Description
    On Error GoTo 0
    calculateButton.Enabled = True
    If number = 0 Then
        Unload Me
    Else
        Me.Controls("message").Caption = message
    End If
End Sub

' On ferme sans changer le résultat déjà affiché
Private Sub cancelButton_Click()
    Unload Me
End Sub
