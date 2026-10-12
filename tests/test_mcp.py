import asyncio
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from paintsdb.mcp_server import MCPServer
from paintsdb.service import OPERATIONS
from test_service import service


def test_mcp_transport_auth_crud_context_and_shared_state(service,tmp_path):
    server=MCPServer(service,port=0).start()
    try:
        assert httpx.post(server.url,json={"jsonrpc":"2.0","method":"ping","id":1}).status_code==401
        assert httpx.post(server.url,headers={"Authorization":"Bearer "+server.token,"Origin":"https://example.org"},json={}).status_code==401
        async def scenario():
            async with httpx.AsyncClient(headers={"Authorization":"Bearer "+server.token}) as client:
                async with streamable_http_client(server.url,http_client=client) as (read,write,_):
                    async with ClientSession(read,write) as session:
                        await session.initialize()
                        listed=await session.list_tools()
                        assert len(listed.tools)==len(OPERATIONS)
                        for tool in listed.tools:
                            if tool.name not in ("paints_status","paints_events","paints_evaluate_mass","paints_open_database","paints_create_database"):
                                assert "context" in tool.inputSchema['required']
                        result=await session.call_tool("paints_status",{})
                        context=result.structuredContent['data']['context']
                        result=await session.call_tool("paints_save_component",dict(context=context,code="MCP-1",name="Тест MCP",aliases=["тест"],price=dict(period="2026-01",package_price=1000,volume_liters=1,grams_per_liter=1000)))
                        assert not result.isError,result
                        identity=result.structuredContent['data']['id']
                        result=await session.call_tool("paints_save_recipe",dict(context=context,lines=[dict(component_id=identity,mass_expression="20+15+кап")]))
                        assert not result.isError,result
                        recipe=result.structuredContent['data']
                        assert recipe['snapshot_total']==36
                        assert service.get_recipe(recipe['id'])['source']=='mcp'
                        result=await session.call_tool("paints_list_recipes",dict(context=context))
                        assert not result.isError and len(result.structuredContent['data'])==1
                        result=await session.call_tool("paints_save_recipe",dict(context=context,id=recipe['id'],revision=recipe['revision'],name="Правка MCP",lines=recipe['lines']))
                        assert not result.isError,result
                        revision=result.structuredContent['data']['revision']
                        result=await session.call_tool("paints_delete_recipe",dict(context=context,id=recipe['id'],revision=revision))
                        assert not result.isError
                        result=await session.call_tool("paints_create_database",dict(context=context,path=str(tmp_path/'mcp-new.paintsdb')))
                        assert not result.isError,result
                        result=await session.call_tool("paints_delete_component",dict(context=context,id=identity,revision=1))
                        assert result.isError
        asyncio.run(scenario())
    finally:
        server.stop()
