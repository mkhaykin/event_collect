# TODO надо переделать на класс который строит эти запросы. Может с фильтрацией и с типом журнала
# Но вообще это в отдельный класс


def get_ps_script(
    limit: int = 1_000,
    log_name: str = "System",
    last_record_id: int = -1,
) -> str:
    xml_filter_query = """
$filterXml = '<QueryList>
  <Query Id="0" Path="%s">
    <Select Path="%s">*[System[Channel="%s" and EventRecordID > %s]]</Select>
  </Query>
</QueryList>'""" % (log_name, log_name, log_name, last_record_id)

    return """# Переключаем язык потока на английский
[System.Threading.Thread]::CurrentThread.CurrentCulture = New-Object "System.Globalization.CultureInfo" "en-US";
[System.Threading.Thread]::CurrentThread.CurrentUICulture = New-Object "System.Globalization.CultureInfo" "en-US";

%s

Get-WinEvent -FilterXml $filterXml -MaxEvents %s -Oldest -ErrorAction SilentlyContinue | ForEach-Object {
    $xml = [xml]$_.ToXml()
    $systemNode = $xml.Event.System
    $eventDataNode = $xml.Event.EventData

    $item = [PSCustomObject]@{
        system=[PSCustomObject]@{
            provider=[PSCustomObject]@{
                name=$systemNode.Provider.Name
                guid=$systemNode.Provider.Guid
                event_source_name=$systemNode.Provider.EventSourceName
                resource_file_name=$systemNode.Provider.ResourceFileName
                message_file_name=$systemNode.Provider.messageFileName
            }
            event_id=if ($systemNode.EventID -is [string]) { $systemNode.EventID } else { $systemNode.EventID.InnerText }
            event_record_id = $systemNode.EventRecordID
            event=[PSCustomObject]@{
                qualifiers = if ($systemNode.EventID -is [string]) { $null } else {$systemNode.EventID.GetAttribute("Qualifiers")}
            }
            version=if ($systemNode.Version -is [string]) {$systemNode.Version} else {$systemNode.Version.InnerText}
            level=if ($systemNode.Level -is [string]) {$systemNode.Level} else {$systemNode.Level.InnerText}

            task=$systemNode.Task
            opcode=$systemNode.Opcode
            keywords=$systemNode.Keywords

            time_created=$systemNode.TimeCreated.SystemTime

            correlation= [PSCustomObject]@{
                activity_id         = $systemNode.Correlation.ActivityID
                related_activity_id = $systemNode.Correlation.RelatedActivityID
            }
            execution=[PSCustomObject]@{
                process_id=$systemNode.Execution.ProcessID
                thread_id=$systemNode.Execution.ThreadID
            }
            channel=$systemNode.Channel
            computer=$systemNode.Computer
            security=[PSCustomObject]@{
                user_id = $systemNode.Security.UserID
            }
        }

        event_data = if ($null -ne $eventDataNode) {
            $eventDataNode.InnerXml
        } else { $null }

        binary_data = if ($null -ne $binaryNode) {
            $binaryNode.InnerText
        } else { $null }

        user_data = if ($null -ne $userDataNode) {
            $userDataNode.InnerXml
        } else { $null }

        message=$_.Message
    }

    $item | ConvertTo-Json -Compress
}
""" % (xml_filter_query, limit)  # noqa: E501
