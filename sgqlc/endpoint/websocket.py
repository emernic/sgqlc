from sgqlc.endpoint.base import BaseEndpoint
import websocket
import uuid
import json


class WebSocketEndpoint(BaseEndpoint):
    '''
    A synchronous websocket endpoint for graphql queries or subscriptions
    '''
    def __init__(self, url, **ws_options):
        '''
        :param url: ws:// or wss:// url to connect to
        :type url: str

        :param ws_options: options to pass to websocket.create_connection
        :type ws_options: dict
        '''
        self.url = url
        self.ws_options = ws_options
        self.keep_alives = ['ka']

    def __str__(self):
        return '%s(url=%s, ws_options=%s)' % (
            self.__class__.__name__, self.url, self.ws_options)

    def __call__(self, query, variables=None, operation_name=None):
        '''
        Makes a single query over the websocket

        :param query: the GraphQL query or mutation to execute. Note
          that this is converted using ``bytes()``, thus one may pass
          an object implementing ``__bytes__()`` method to return the
          query, eventually in more compact form (no indentation, etc).
        :type query: :class:`str` or :class:`bytes`.

        :param variables: variables (dict) to use with
          ``query``. This is only useful if the query or
          mutation contains ``$variableName``.
        :type variables: dict

        :param operation_name: if more than one operation is listed in
          ``query``, then it should specify the one to be executed.
        :type operation_name: str

        :return: generator of dicts with optional fields ``data`` containing
          the GraphQL returned data as nested dict and ``errors`` with
          an array of errors. Note that both ``data`` and ``errors`` may
          be returned in each dict!
          Will generate a single element for ``query`` operations,
          where data lists are generally embedded within the result structure.
          For ``subscription`` operations, will generate a dict for each
          subscription notification.

        :rtype: generator
        '''
        if isinstance(query, bytes):
            query = query.decode('utf-8')
        elif not isinstance(query, str):
            # allows sgqlc.operation.Operation to be passed
            # and generate compact representation of the queries
            query = bytes(query).decode('utf-8')
        ws = websocket.create_connection(self.url,
                                         subprotocols=['graphql-ws'],
                                         **self.ws_options)
        try:
            init_id = self.generate_id()
            ws.send(json.dumps({'type': 'connection_init', 'id': init_id}))
            response = self._get_response(ws)
            if response['type'] != 'connection_ack':
                raise ValueError(
                    f'Unexpected {response["type"]} '
                    f'when waiting for connection ack'
                )
            # response does not always have an id
            if response.get('id', init_id) != init_id:
                raise ValueError(
                    f'Unexpected id {response["id"]} '
                    f'when waiting for connection ack'
                )

            query_id = self.generate_id()
            ws.send(json.dumps({'type': 'start',
                                'id': query_id,
                                'payload': {'query': query,
                                            'variables': variables,
                                            'operationName': operation_name}}))
            response = self._get_response(ws)
            while response['type'] != 'complete':
                if response['id'] != query_id:
                    raise ValueError(
                        f'Unexpected id {response["id"]} '
                        f'when waiting for query results'
                    )
                if response['type'] == 'data':
                    yield response['payload']
                else:
                    raise ValueError(f'Unexpected message {response} '
                                     f'when waiting for query results')
                response = self._get_response(ws)

        finally:
            ws.close()

    def _get_response(self, ws):
        '''Ignore any keep alive responses'''

        response = json.loads(ws.recv())
        while response['type'] in self.keep_alives:
            response = json.loads(ws.recv())
        return response

    @staticmethod
    def generate_id() -> str:
        return str(uuid.uuid4())
