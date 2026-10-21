# Rollback de modelo e serving

## Diagnóstico

Consulte `/health/ready` para identificar nome e versão em execução, a imagem/revisão no
Container Apps e os logs de erro/latência. Compare com o resumo do último deploy no GitHub.
Não registe payloads com dados de clientes durante o diagnóstico.

## Registry local

`hotelml status` mostra os aliases. `hotelml rollback` troca `champion` e `previous_champion`.
Esse comando falha se não houver versão anterior. Verifique novamente com `hotelml status`.
Na API local sem bundle, reinicie o Uvicorn e confirme a versão em `/health/ready`.
Na API com bundle, a troca de alias não altera o modelo empacotado.

## API Azure

Escolha a imagem por digest de uma revisão conhecida e saudável; não use uma tag mutável.
Os comandos abaixo são para PowerShell com Azure CLI autenticada:

```powershell
az containerapp revision list --name '<app>' --resource-group '<rg>' -o table
az containerapp revision show --name '<app>' --resource-group '<rg>' --revision '<revisao-saudavel>' --query properties.template.containers
az containerapp update --name '<app>' --resource-group '<rg>' --image '<acr>/hotelml@sha256:<digest-anterior>'
python scripts/smoke_api.py 'https://<fqdn>' --version '<versao-anterior>'
```

Uma nova revisão reutiliza a imagem anterior. Confirme readiness e previsões antes de encerrar
o incidente. O modo Single envia tráfego à revisão nova quando estiver pronta; uma revisão que
falha na readiness não deve substituir a saudável. Em falhas funcionais com readiness saudável,
é necessária esta intervenção: não há deteção funcional nem rollback automático nesta fase.

Se o próximo CD deve manter a versão antiga, reverta também o alias no registry que alimenta o
workflow e confirme `hotelml status` nesse backend. Registe os digests, versões, motivo, impacto
e horário da recuperação; isso alimentará o post-mortem da fase 6.
