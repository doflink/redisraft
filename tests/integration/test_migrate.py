from _pytest.python_api import raises
from redis import ResponseError


def test_migration_basic(cluster_factory):
    """
    Simulates full migration process. Test generates keys in a cluster and moves
    half of the keys to another cluster.
    """

    cluster1 = cluster_factory().create(3, raft_args={
        'sharding': 'yes',
        'external-sharding': 'yes'})
    cluster2 = cluster_factory().create(3, raft_args={
        'sharding': 'yes',
        'external-sharding': 'yes'})

    key_count = 11500

    # Fill two specific slots with keys. One of these slots will be migrated.
    for i in range(key_count):
        cluster1.execute('set', '{key}' + str(i), 'value')   # slot 12539
        cluster1.execute('set', '{key2}' + str(i), 'value')  # slot 4998

    cluster1_dbid = cluster1.leader_node().info()['raft_dbid']
    cluster2_dbid = cluster2.leader_node().info()['raft_dbid']

    # Set slot range 8001-16383 as migrating from cluster1 to cluster2.
    assert cluster1.execute(
        'RAFT.SHARDGROUP', 'REPLACE',
        '2',
        cluster1_dbid,
        '2', '3',
        '0', '8000', '1', '123', '8001', '16383', '3', '123',
        '%s00000001' % cluster1_dbid, 'localhost:%s' % cluster1.node(1).port,
        '%s00000002' % cluster1_dbid, 'localhost:%s' % cluster1.node(2).port,
        '%s00000003' % cluster1_dbid, 'localhost:%s' % cluster1.node(3).port,
        cluster2_dbid,
        '1', '3',
        '8001', '16383', '2', '123',
        '%s00000001' % cluster2_dbid, 'localhost:%s' % cluster2.node(1).port,
        '%s00000002' % cluster2_dbid, 'localhost:%s' % cluster2.node(2).port,
        '%s00000003' % cluster2_dbid, 'localhost:%s' % cluster2.node(3).port,
        ) == b'OK'

    assert cluster2.execute(
        'RAFT.SHARDGROUP', 'REPLACE',
        '2',
        cluster1_dbid,
        '2', '3',
        '0', '8000', '1', '123', '8001', '16383', '3', '123',
        '%s00000001' % cluster1_dbid, 'localhost:%s' % cluster1.node(1).port,
        '%s00000002' % cluster1_dbid, 'localhost:%s' % cluster1.node(2).port,
        '%s00000003' % cluster1_dbid, 'localhost:%s' % cluster1.node(3).port,
        cluster2_dbid,
        '1', '3',
        '8001', '16383', '2', '123',
        '%s00000001' % cluster2_dbid, 'localhost:%s' % cluster2.node(1).port,
        '%s00000002' % cluster2_dbid, 'localhost:%s' % cluster2.node(2).port,
        '%s00000003' % cluster2_dbid, 'localhost:%s' % cluster2.node(3).port,
        ) == b'OK'

    # Migrate keys
    cursor = 0
    while True:
        reply = cluster1.execute('raft.scan', str(cursor), '8001-16383')

        cursor = int(reply[0])
        keys = reply[1]

        if len(keys) != 0:
            key_names = []
            for key in keys:
                key_names.append(key[0].decode('utf-8'))

            assert cluster1.execute('migrate', '', '', '', '', '', 'keys',
                                    *key_names) == b'OK'

        # If cursor is zero, we've moved all the keys
        if cursor == 0:
            break

    # Finalize migration
    assert cluster1.execute(
        'RAFT.SHARDGROUP', 'REPLACE',
        '2',
        cluster1_dbid,
        '1', '3',
        '0', '8000', '1', '123',
        '%s00000001' % cluster1_dbid, 'localhost:%s' % cluster1.node(1).port,
        '%s00000002' % cluster1_dbid, 'localhost:%s' % cluster1.node(2).port,
        '%s00000003' % cluster1_dbid, 'localhost:%s' % cluster1.node(3).port,
        cluster2_dbid,
        '1', '3',
        '8001', '16383', '1', '123',
        '%s00000001' % cluster2_dbid, 'localhost:%s' % cluster2.node(1).port,
        '%s00000002' % cluster2_dbid, 'localhost:%s' % cluster2.node(2).port,
        '%s00000003' % cluster2_dbid, 'localhost:%s' % cluster2.node(3).port,
        ) == b'OK'

    assert cluster2.execute(
        'RAFT.SHARDGROUP', 'REPLACE',
        '2',
        cluster1_dbid,
        '1', '3',
        '0', '8000', '1', '123',
        '%s00000001' % cluster1_dbid, 'localhost:%s' % cluster1.node(1).port,
        '%s00000002' % cluster1_dbid, 'localhost:%s' % cluster1.node(2).port,
        '%s00000003' % cluster1_dbid, 'localhost:%s' % cluster1.node(3).port,
        cluster2_dbid,
        '1', '3',
        '8001', '16383', '1', '123',
        '%s00000001' % cluster2_dbid, 'localhost:%s' % cluster2.node(1).port,
        '%s00000002' % cluster2_dbid, 'localhost:%s' % cluster2.node(2).port,
        '%s00000003' % cluster2_dbid, 'localhost:%s' % cluster2.node(3).port,
        ) == b'OK'

    # Sanity check

    # cluster-1 has slots 0-8000
    assert cluster1.execute('dbsize') == key_count
    assert cluster1.node(1).execute('get', '{key2}1') == b'value'
    with raises(ResponseError, match='MOVED 12539'):
        cluster1.node(1).execute('get', '{key}1')

    # cluster-2 has slots 8001-16383
    assert cluster2.execute('dbsize') == key_count
    assert cluster2.node(1).execute('get', '{key}1') == b'value'
    with raises(ResponseError, match='MOVED 4998'):
        cluster2.node(1).execute('get', '{key2}1')


def test_raft_import(cluster):
    cluster.create(3, raft_args={'sharding': 'yes', 'external-sharding': 'yes'})
    assert cluster.execute('set', 'key', 'value')
    assert cluster.execute('get', 'key') == b'value'

    serialized = cluster.execute('dump', 'key')
    assert cluster.execute('del', 'key') == 1

    assert cluster.execute('get', 'key') is None

    assert cluster.execute(
        'RAFT.SHARDGROUP', 'REPLACE',
        '2',

        '12345678901234567890123456789013',
        '1', '1',
        '0', '16383', '3', '123',
        '1234567890123456789012345678901334567890', '3.3.3.3:3333',

        cluster.leader_node().info()["raft_dbid"],
        '1', '1',
        '0', '16383', '2', '123',
        '1234567890123456789012345678901234567890', '2.2.2.2:2222',
    ) == b'OK'

    # initial import
    assert cluster.execute('raft.import', '2', '123', 'key', serialized) == b'OK'
    # older term, fails
    with raises(ResponseError, match='invalid term'):
        assert cluster.execute('raft.import', '1', '123', 'key', serialized)
    # not matched session migration key
    with raises(ResponseError, match='invalid migration_session_key'):
        assert cluster.execute('raft.import', '2', '10', 'key', serialized)
    # repeated with correct values
    assert cluster.execute('raft.import', '2', '123', 'key', serialized) == b'OK'
    # repeated with updated term
    assert cluster.execute('raft.import', '3', '123', 'key', serialized) == b'OK'
    # again, older, previously valid term
    with raises(ResponseError, match='invalid term'):
        assert cluster.execute('raft.import', '2', '123', 'key', serialized)

    conn = cluster.leader_node().client.connection_pool.get_connection('deferred')
    conn.send_command('ASKING')
    assert conn.read_response() == b'OK'

    conn.send_command('get', 'key')
    assert conn.read_response() == b'value'


def test_import_with_snapshot(cluster):
    cluster.create(1, raft_args={'sharding': 'yes', 'external-sharding': 'yes'})
    assert cluster.execute('set', 'key', 'value')
    assert cluster.execute('get', 'key') == b'value'

    serialized = cluster.execute('dump', 'key')
    assert cluster.execute('del', 'key') == 1

    assert cluster.execute('get', 'key') is None

    assert cluster.execute(
        'RAFT.SHARDGROUP', 'REPLACE',
        '2',
        '12345678901234567890123456789013',
        '1', '1',
        '0', '16383', '3', '123',
        '1234567890123456789012345678901334567890', '3.3.3.3:3333',
        cluster.leader_node().info()["raft_dbid"],
        '1', '1',
        '0', '16383', '2', '123',
        '1234567890123456789012345678901234567890', '2.2.2.2:2222',
    ) == b'OK'

    # initial import
    assert cluster.execute('raft.import', '2', '123', 'key', serialized) == b'OK'

    assert cluster.node(1).client.execute_command(
        'RAFT.DEBUG', 'COMPACT') == b'OK'

    cluster.node(1).kill()
    cluster.node(1).start()
    cluster.node(1).wait_for_info_param('raft_state', 'up')

    # incorrect session migration key
    with raises(ResponseError, match="invalid migration_session_key"):
        cluster.execute('raft.import', '2', '0', 'key', serialized)

    # older term should not be accepted
    with raises(ResponseError, match="invalid term"):
        cluster.execute('raft.import', '1', '123', 'key', serialized)

    # same term should still work after snapshot load
    assert cluster.execute('raft.import', '2', '123', 'key', serialized) == b'OK'


def test_happy_migrate(cluster_factory):
    cluster1 = cluster_factory().create(1, raft_args={
        'sharding': 'yes',
        'external-sharding': 'yes'})
    cluster2 = cluster_factory().create(1, raft_args={
        'sharding': 'yes',
        'external-sharding': 'yes'})

    cluster1_dbid = cluster1.leader_node().info()["raft_dbid"]
    cluster2_dbid = cluster2.leader_node().info()["raft_dbid"]

    assert cluster1.execute('set', 'key', 'value')
    assert cluster1.execute('get', 'key') == b'value'
    assert cluster1.execute('set', '{key}key1', 'value1')
    assert cluster1.execute('get', '{key}key1') == b'value1'

    assert cluster1.execute(
        'RAFT.SHARDGROUP', 'REPLACE',
        '2',
        cluster2_dbid,
        '1', '1',
        '0', '16383', '2', '123',
        '%s00000001' % cluster2_dbid, 'localhost:%s' % cluster2.node(1).port,
        cluster1_dbid,
        '1', '1',
        '0', '16383', '3', '123',
        '%s00000001' % cluster1_dbid, 'localhost:%s' % cluster1.node(1).port,
        ) == b'OK'

    assert cluster2.execute(
        'RAFT.SHARDGROUP', 'REPLACE',
        '2',
        cluster2_dbid,
        '1', '1',
        '0', '16383', '2', '123',
        '%s00000001' % cluster2_dbid, 'localhost:%s' % cluster2.node(1).port,
        cluster1_dbid,
        '1', '1',
        '0', '16383', '3', '123',
        '%s00000001' % cluster1_dbid, 'localhost:%s' % cluster1.node(1).port,
        ) == b'OK'

    assert cluster1.execute("migrate", "", "", "", "", "", "keys", "key", "{key}key1") == b'OK'

    with raises(ResponseError, match="ASK 12539 localhost"):
        cluster1.execute("get", "key")

    with raises(ResponseError, match="ASK 12539 localhost"):
        cluster1.execute("get", "{key}key1")

    with raises(ResponseError, match="MOVED 12539 localhost"):
        # can't use cluster.execute() as that will try to handle the MOVED response itself
        cluster2.leader_node().client.get("key")

    conn = cluster2.leader_node().client.connection_pool.get_connection('deferred')
    conn.send_command('ASKING')
    assert conn.read_response() == b'OK'

    conn.send_command('get', 'key')
    assert conn.read_response() == b'value'

    conn.send_command('get', '{key}key1')
    with raises(ResponseError, match="MOVED 12539 localhost:5001"):
        conn.read_response()

    conn.send_command('ASKING')
    assert conn.read_response() == b'OK'
    conn.send_command('get', '{key}key1')
    assert conn.read_response() == b'value1'

    conn.send_command('get', 'key1')
    with raises(ResponseError, match="MOVED 9189 localhost:5001"):
        conn.read_response()

    conn.send_command('ASKING')
    assert conn.read_response() == b'OK'
    conn.send_command('get', 'key1')
    with raises(ResponseError, match="TRYAGAIN"):
        conn.read_response()

    assert cluster2.execute(
        'RAFT.SHARDGROUP', 'REPLACE',
        '1',
        cluster2_dbid,
        '1', '1',
        '0', '16383', '1', "123",
        '%s00000001' % cluster2_dbid, 'localhost:%s' % cluster2.node(1).port,
        ) == b'OK'

    assert cluster2.execute("get", "key") == b'value'
    assert cluster2.execute("get", "{key}key1") == b'value1'
    assert cluster2.execute("get", "key1") is None


def test_sad_path_migrate(cluster_factory):
    cluster1 = cluster_factory().create(1, raft_args={
        'sharding': 'yes',
        'external-sharding': 'yes'})
    cluster2 = cluster_factory().create(1, raft_args={
        'sharding': 'yes',
        'external-sharding': 'yes'})

    cluster1_dbid = cluster1.leader_node().info()["raft_dbid"]
    cluster2_dbid = cluster2.leader_node().info()["raft_dbid"]

    assert cluster1.execute('set', 'key1', 'value1')
    assert cluster1.execute('get', 'key1') == b'value1'
    assert cluster1.execute('set', 'key2', 'value2')
    assert cluster1.execute('get', 'key2') == b'value2'
    assert cluster1.execute('set', 'key3', 'value3')
    assert cluster1.execute('get', 'key3') == b'value3'

    assert cluster1.execute(
        'RAFT.SHARDGROUP', 'REPLACE',
        '2',
        cluster2_dbid,
        '1', '1',
        '0', '16383', '2', '123',
        '%s00000001' % cluster2_dbid, 'localhost:%s' % cluster2.node(1).port,
        cluster1_dbid,
        '1', '1',
        '0', '16383', '3', '123',
        '%s00000001' % cluster1_dbid, 'localhost:%s' % cluster1.node(1).port,
        ) == b'OK'

    assert cluster2.execute(
        'RAFT.SHARDGROUP', 'REPLACE',
        '2',
        cluster2_dbid,
        '1', '1',
        '0', '16383', '2', '123',
        '%s00000001' % cluster2_dbid, 'localhost:%s' % cluster2.node(1).port,
        cluster1_dbid,
        '1', '1',
        '0', '16383', '3', '123',
        '%s00000001' % cluster1_dbid, 'localhost:%s' % cluster1.node(1).port,
        ) == b'OK'

    def validate_failed_migration(key_name, value, slot, err_string):
        # first pass, should error out
        with raises(ResponseError, match=err_string):
            cluster1.execute("migrate", "", "", "", "", "", "keys", key_name)

        # validate state
        with raises(ResponseError, match="TRYAGAIN"):
            cluster1.execute("get", key_name)
        with raises(ResponseError, match=f"MOVED {slot} localhost"):
            cluster2.leader_node().client.get(key_name)

        # remove injected error, should pass
        cluster1.execute("raft.debug", "migration_debug", 'none')
        assert cluster1.execute("migrate", "", "", "", "", "", "keys", key_name) == b'OK'

        # validate state
        with raises(ResponseError, match=f"ASK {slot} localhost"):
            cluster1.execute("get", key_name)
        with raises(ResponseError, match=f"MOVED {slot} localhost"):
            cluster2.leader_node().client.get(key_name)

        conn = cluster2.leader_node().client.connection_pool.get_connection('deferred')
        conn.send_command('ASKING')
        assert conn.read_response() == b'OK'
        conn.send_command('get', key_name)
        assert conn.read_response() == value

    cluster1.execute("raft.debug", "migration_debug", 'fail_connect')
    validate_failed_migration("key1", b'value1', 9189, "failed to connect to import cluster, try again")
    cluster1.execute("raft.debug", "migration_debug", 'fail_import')
    validate_failed_migration("key2", b'value2', 4998, "failed to submit RAFT.IMPORT command, try again")
    cluster1.execute("raft.debug", "migration_debug", 'fail_unlock')
    validate_failed_migration("key3", b'value3', 935, "Unable to unlock/delete migrated keys, try again")


def test_redirect_asking_to_leader(cluster):
    """
    Followers redirect asking mode requests to the leader with an ASK reply.
    """
    cluster.create(3)

    # Leader is node-2
    cluster.leader_node().transfer_leader(2)

    # Send a request to node-3
    follower = cluster.node(3)
    follower.execute('ASKING')

    # Expect redirection to node-2
    with raises(ResponseError, match="ASK 12539 localhost:5002"):
        follower.execute('get', 'key')
