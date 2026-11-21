Attribute VB_Name = "WorkbookUI"
Option Explicit

Private Const FormWidth As Double = 620
Private Const FormHeight As Double = 500
Private Const SavedFirstRow As Long = 40
Private Const GreekNames As String = "delta,gamma,vega,theta,rho,vanna,volga,charm,speed"

' On ouvre le formulaire depuis le bouton de la feuille de résultats
Public Sub SaisirOption()
    UserForm1.Show
End Sub

' On regroupe les paramètres du contrat et ceux du marché dans deux colonnes
Public Sub BuildForm(ByVal form As Object)
    Dim specs() As String, index As Long
    form.Caption = "Paramètres de l'option"
    form.Width = FormWidth
    form.Height = FormHeight
    form.BackColor = RGB(247, 248, 250)
    form.Font.Name = "Segoe UI"
    form.Font.Size = 9
    specs = Split(ContractFields() & vbLf & MarketFields(), vbLf)
    For index = 0 To UBound(specs)
        AddField form, specs(index), index
    Next index
    AddSwitch form, "pruning", "Pruning (trinomial)", 20, True
    AddSwitch form, "includeGreeks", "Calculer les neuf grecs", 320, True
    AddButton form, "calculate", "Calculer", 420
    AddButton form, "cancel", "Fermer", 320
    AddLabel form, "message", "Taux et volatilité en % · Dates au format AAAA-MM-JJ", 20, 440, 285
    form.Controls("message").Height = 28
End Sub

' On décrit les champs sans répéter le code de création des contrôles
Private Function ContractFields() As String
    ContractFields = "kind|Produit|Call|Call;Put;Digitale call;Digitale put;One-touch haut" & vbLf & _
        "strike|Strike / barrière (EUR)|100|" & vbLf & _
        "exercise|Exercice|Européen|Européen;Américain" & vbLf & _
        "expiry|Échéance (AAAA-MM-JJ)|2027-10-29|" & vbLf & _
        "quantity|Quantité signée|1|" & vbLf & _
        "multiplier|Multiplicateur|1|" & vbLf & _
        "payout|Versement des produits binaires (EUR)|1|" & vbLf & _
        "monitoring|Observation du one-touch|Continue|Continue;Dates de l'arbre"
End Function

' On distingue le dividende fixe du rendement continu et les dates des durées
Private Function MarketFields() As String
    MarketFields = "spot|Prix de l'action (EUR)|100|" & vbLf & _
        "volatility|Volatilité annuelle (%)|20|" & vbLf & _
        "rate|Taux sans risque annuel (%)|3|" & vbLf & _
        "yield|Rendement continu annuel (%)|0|" & vbLf & _
        "valuation|Date de valorisation|2026-10-29|" & vbLf & _
        "dividend|Dividende fixe (EUR)|0|" & vbLf & _
        "exdate|Date ex-dividende|2027-06-09|" & vbLf & _
        "basis|Convention de jours|365|365;360" & vbLf & _
        "steps|Nombre de pas|300|" & vbLf & _
        "mode|Arbre|Trinomial|Trinomial;Binomial"
End Function

' On conserve les dernières saisies pour la prochaine ouverture du formulaire
Private Sub AddField(ByVal form As Object, ByVal spec As String, ByVal index As Long)
    Dim fields() As String, choices() As String, control As Object, choice As Long
    Dim left As Double, top As Double, saved As String
    fields = Split(spec, "|")
    left = 20 + IIf(index < 8, 0, 300)
    top = 16 + IIf(index < 8, index, index - 8) * 38
    AddLabel form, fields(0) & "Label", fields(1), left, top, 280
    If fields(3) = "" Then
        Set control = form.Controls.Add("Forms.TextBox.1", fields(0), True)
    Else
        Set control = form.Controls.Add("Forms.ComboBox.1", fields(0), True)
        control.Style = 2
        choices = Split(fields(3), ";")
        For choice = 0 To UBound(choices)
            control.AddItem choices(choice)
        Next choice
    End If
    control.Move left, top + 14, 274, 20
    saved = SavedField(index)
    control.Value = IIf(saved = "", fields(2), saved)
End Sub

' On conserve les dates ISO lors de la réouverture quelle que soit la langue d'Excel
Private Function SavedField(ByVal index As Long) As String
    Dim value As String
    value = CStr(Feuil1.Cells(index + SavedFirstRow, 2).Value)
    If TypeName(Feuil1.Cells(index + SavedFirstRow, 2).Value) = "Date" Then
        SavedField = Format$(Feuil1.Cells(index + SavedFirstRow, 2).Value, "yyyy-mm-dd")
    Else
        SavedField = CStr(value)
    End If
End Function
' On affiche des libellés lisibles au-dessus des champs
Private Sub AddLabel(ByVal form As Object, ByVal name As String, ByVal caption As String, _
    ByVal left As Double, ByVal top As Double, ByVal width As Double)
    Dim label As Object
    Set label = form.Controls.Add("Forms.Label.1", name, True)
    label.Move left, top, width, 14
    label.Caption = caption
    label.BackStyle = 0
    label.ForeColor = RGB(54, 65, 76)
End Sub

' On propose les deux choix utiles sans exposer les réglages des différences finies
Private Sub AddSwitch(ByVal form As Object, ByVal name As String, ByVal caption As String, _
    ByVal left As Double, ByVal value As Boolean)
    Dim control As Object
    Set control = form.Controls.Add("Forms.CheckBox.1", name, True)
    control.Move left, 410, 260, 18
    control.Caption = caption
    control.Value = value
End Sub

' On garde les boutons de validation et de fermeture au même endroit
Private Sub AddButton(ByVal form As Object, ByVal name As String, ByVal caption As String, ByVal left As Double)
    Dim control As Object
    Set control = form.Controls.Add("Forms.CommandButton.1", name, True)
    control.Move left, 440, 90, 26
    control.Caption = caption
End Sub

' On accepte le point ou la virgule pour les paramètres numériques
Private Function InputNumber(ByVal form As Object, ByVal name As String) As Double
    Dim text As String
    text = Trim$(CStr(form.Controls(name).Value))
    If text = "" Then Err.Raise 5, , "Renseigner le champ " & name
    InputNumber = CDbl(Replace(text, ".", Application.DecimalSeparator))
End Function

' On lit les dates de façon identique quelle que soit la langue d'Excel
Private Function InputDate(ByVal form As Object, ByVal name As String) As Date
    Dim fields() As String, value As Date
    fields = Split(CStr(form.Controls(name).Value), "-")
    If UBound(fields) <> 2 Then Err.Raise 5, , "Date attendue : AAAA-MM-JJ"
    value = DateSerial(CInt(fields(0)), CInt(fields(1)), CInt(fields(2)))
    If Format$(value, "yyyy-mm-dd") <> CStr(form.Controls(name).Value) Then Err.Raise 5, , "Date invalide"
    InputDate = value
End Function

' On convertit les dates en années et les pourcentages en décimaux pour le moteur
Private Function FormParameters(ByVal form As Object) As String
    Dim values(0 To 23) As String, index As Long, basis As Double, valuation As Date, expiry As Date
    basis = InputNumber(form, "basis")
    valuation = InputDate(form, "valuation")
    expiry = InputDate(form, "expiry")
    If expiry <= valuation Then Err.Raise 5, , "L'échéance doit suivre la valorisation"
    For index = 0 To 23
        values(index) = "0"
    Next index
    values(0) = Pricer.NumberText(InputNumber(form, "spot"))
    values(1) = Pricer.NumberText(InputNumber(form, "rate") / 100)
    values(2) = Pricer.NumberText(InputNumber(form, "volatility") / 100)
    values(3) = Pricer.NumberText(InputNumber(form, "yield") / 100)
    values(4) = Pricer.NumberText(InputNumber(form, "dividend"))
    If Val(values(4)) > 0 Then values(5) = Pricer.NumberText((InputDate(form, "exdate") - valuation) / basis)
    values(6) = Pricer.NumberText((expiry - valuation) / basis)
    values(7) = Pricer.NumberText(InputNumber(form, "steps"))
    values(8) = IIf(form.Controls("mode").Value = "Trinomial", "3", "2")
    values(9) = IIf(form.Controls("pruning").Value And values(8) = "3", "0.0000000001", "0")
    ContractParameters form, values, basis
    FormParameters = Join(values, vbTab)
End Function

' On traduit les choix du formulaire vers les conventions déjà utilisées par le site
Private Sub ContractParameters(ByVal form As Object, ByRef values() As String, ByVal basis As Double)
    Dim kinds() As String
    kinds = Split("call,put,digital_call,digital_put,one_touch_up", ",")
    values(10) = kinds(form.Controls("kind").ListIndex)
    values(11) = Pricer.NumberText(InputNumber(form, "strike"))
    values(12) = IIf(form.Controls("exercise").Value = "Américain", "1", "0")
    If values(10) <> "call" And values(10) <> "put" And values(12) = "1" Then
        Err.Raise 5, , "L'exercice américain concerne les calls et puts"
    End If
    values(13) = Pricer.NumberText(InputNumber(form, "payout"))
    values(14) = IIf(form.Controls("monitoring").Value = "Continue", "continuous", "grid")
    values(15) = ""
    values(20) = Pricer.NumberText(InputNumber(form, "spot") * 0.02)
    values(21) = "0.005"
    values(22) = "0.001"
    values(23) = Pricer.NumberText(1 / basis)
    If Val(values(0)) <= 0 Or Val(values(2)) <= 0 Or Val(values(4)) < 0 Then Err.Raise 5, , "Marché invalide"
    If Val(values(7)) < 1 Or Val(values(7)) <> Fix(Val(values(7))) Then Err.Raise 5, , "Nombre de pas invalide"
    If Val(values(11)) < 0 Or Val(values(13)) < 0 Then Err.Raise 5, , "Strike ou versement invalide"
End Sub

' On calcule avant de remplacer les résultats et de mémoriser les nouvelles saisies
Public Sub ComputeForm(ByVal form As Object)
    Dim parameters As String, names As String, result As String, quantity As Double, multiplier As Double
    Dim parts() As String
    parameters = FormParameters(form)
    quantity = InputNumber(form, "quantity")
    multiplier = InputNumber(form, "multiplier")
    If multiplier <= 0 Then Err.Raise 5, , "Le multiplicateur doit être positif"
    names = IIf(form.Controls("includeGreeks").Value, GreekNames, "delta")
    result = Pricer.RunBatch(parameters, names)
    If Left$(result, 6) = "error:" Then Err.Raise 5, , Mid$(result, 7)
    parts = Split(result, vbTab)
    WriteResults form, parts, names, quantity * multiplier
    SaveFields form
End Sub

' On mémorise uniquement les champs saisis et non un ancien résultat de calcul
Private Sub SaveFields(ByVal form As Object)
    Dim specs() As String, field() As String, index As Long
    specs = Split(ContractFields() & vbLf & MarketFields(), vbLf)
    For index = 0 To UBound(specs)
        field = Split(specs(index), "|")
        Feuil1.Cells(index + SavedFirstRow, 2).NumberFormat = "@"
        Feuil1.Cells(index + SavedFirstRow, 2).Value = CStr(form.Controls(field(0)).Value)
    Next index
End Sub

' On présente le prix et la couverture avant le détail des grecs
Private Sub WriteResults(ByVal form As Object, ByRef result() As String, ByVal names As String, ByVal weight As Double)
    Dim greeks() As String, index As Long, basis As Double, factor As Double
    basis = InputNumber(form, "basis")
    PrepareSheet
    Feuil2.Cells(4, 1).Value = Val(result(0))
    Feuil2.Cells(4, 3).Value = Val(result(0)) * weight
    If Left$(result(6), 6) <> "error:" Then Feuil2.Cells(4, 5).Value = -Val(result(6)) * weight
    Feuil2.Cells(8, 1).Value = form.Controls("kind").Value & " · " & form.Controls("exercise").Value
    Feuil2.Cells(9, 1).Value = "Strike : " & form.Controls("strike").Value & " EUR"
    Feuil2.Cells(8, 3).Value = "Valorisation : " & form.Controls("valuation").Value
    Feuil2.Cells(9, 3).Value = "Échéance : " & form.Controls("expiry").Value & " · ACT/" & CStr(basis)
    Feuil2.Cells(8, 5).Value = "Quantité × multiplicateur : " & Pricer.NumberText(weight)
    Feuil2.Cells(9, 5).Value = form.Controls("steps").Value & " pas · " & form.Controls("mode").Value
    greeks = Split(names, ",")
    For index = 0 To UBound(greeks)
        WriteGreek greeks(index), CStr(result(index + 6)), index + 14, weight, basis
    Next index
    Feuil2.Cells(26, 1).Value = "Construction : " & Format$(Val(result(1)) * 1000, "0.0") & " ms"
    Feuil2.Cells(26, 3).Value = "Valorisation : " & Format$(Val(result(2)) * 1000, "0.0") & " ms"
    Feuil2.Cells(26, 5).Value = "Total : " & Format$(Val(result(5)) * 1000, "0.0") & " ms"
End Sub

' On affiche les mêmes unités que dans le calculateur web
Private Sub WriteGreek(ByVal name As String, ByVal value As String, ByVal row As Long, _
    ByVal weight As Double, ByVal basis As Double)
    Dim factor As Double, unit As String
    factor = 1
    unit = "EUR / EUR"
    If name = "vega" Or name = "rho" Or name = "vanna" Then factor = 0.01
    If name = "volga" Then factor = 0.0001
    If name = "theta" Or name = "charm" Then factor = 1 / basis
    ' On associe chaque dérivée à son unité d'affichage
    Select Case name
        Case "delta": unit = "actions"
        Case "gamma": unit = "EUR / EUR²"
        Case "vega": unit = "EUR / point de volatilité"
        Case "rho": unit = "EUR / point de taux"
        Case "vanna": unit = "actions / point de volatilité"
        Case "volga": unit = "EUR / point de volatilité²"
        Case "theta": unit = "EUR / jour"
        Case "charm": unit = "actions / jour"
        Case "speed": unit = "EUR / EUR³"
    End Select
    Feuil2.Cells(row, 1).Value = UCase$(Left$(name, 1)) & Mid$(name, 2)
    If Left$(value, 6) = "error:" Then
        Feuil2.Cells(row, 3).Value = "Indisponible"
    Else
        Feuil2.Cells(row, 3).Value = Val(value) * weight * factor
    End If
    Feuil2.Cells(row, 5).Value = unit
End Sub

' On met les résultats en forme sur une seule page imprimable
Private Sub PrepareSheet()
    With Feuil2
        .Cells.UnMerge
        .Cells.Clear
        .Cells.Font.Name = "Aptos"
        .Cells.Font.Size = 11
        .Columns("A:F").ColumnWidth = 18
        .Rows("1:28").RowHeight = 24
        .Range("A1:F1").Merge
        .Cells(1, 1).Value = "Valorisation d'une option"
        .Range("A1:F1").Font.Size = 20
        .Range("A1:F1").Font.Bold = True
        ' On prépare les trois zones de synthèse du prix et de la couverture
        .Range("A3:B3").Merge
        .Range("C3:D3").Merge
        .Range("E3:F3").Merge
        .Cells(3, 1).Value = "Prix unitaire (EUR)"
        .Cells(3, 3).Value = "Valeur de position (EUR)"
        .Cells(3, 5).Value = "Actions de couverture"
        .Range("A4:B5").Merge
        .Range("C4:D5").Merge
        .Range("E4:F5").Merge
        .Range("A4:F5").Font.Size = 20
        .Range("A4:F5").NumberFormat = "#,##0.0000"
        .Range("A3:F5").Interior.Color = RGB(237, 242, 247)
    End With
    FinishSheet
End Sub

' On garde des colonnes aérées et des unités visibles dans le tableau
Private Sub FinishSheet()
    Dim row As Long
    With Feuil2
        For row = 8 To 9
            .Range("A" & row & ":B" & row).Merge
            .Range("C" & row & ":D" & row).Merge
            .Range("E" & row & ":F" & row).Merge
        Next row
        For row = 14 To 22
            .Range("A" & row & ":B" & row).Merge
            .Range("C" & row & ":D" & row).Merge
            .Range("E" & row & ":F" & row).Merge
        Next row
        ' On termine le tableau des grecs et la zone imprimable
        .Range("A12:F12").Merge
        .Cells(12, 1).Value = "Grecs de la position"
        .Cells(12, 1).Font.Bold = True
        .Range("C14:D22").NumberFormat = "0.000000"
        .Range("A8:F9").Font.Size = 10
        .Range("A14:F22").Borders(12).Weight = 2
        .PageSetup.PrintArea = "$A$1:$F$28"
        .PageSetup.Orientation = 2
        .PageSetup.Zoom = False
        .PageSetup.FitToPagesWide = 1
        .PageSetup.FitToPagesTall = 1
    End With
End Sub
