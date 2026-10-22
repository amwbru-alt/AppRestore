from apprevive_core.catalog_discovery import candidate_apps, DiscoveryReporter


def test_only_public_exact_app_identity_is_submitted():
    rows=[{'trackId':'12345678','bundleId':'bank.old','name':'Bank','email':'private@example.test','udid':'private-device','date':'2026-01-01'},
          {'trackId':'12345678','bundleId':'bank.old','name':'Bank'},
          {'trackId':'22345678','name':'Unknown'}, {'trackId':'random','bundleId':'bank.bad','name':'Bad'}]
    assert candidate_apps(rows)==[{'trackId':'12345678','bundleId':'bank.old','name':'Bank','source':'apple_history'}]


def test_retry_after_network_failure_and_no_duplicates_after_acknowledgement():
    calls=[]
    def post(batch):
        calls.append(batch)
        if len(calls)==1:raise OSError('offline')
        return True
    reporter=DiscoveryReporter(post)
    row={'trackId':'12345678','bundleId':'bank.old','name':'Bank'}
    reporter.submit([row]);reporter.submit([row]);reporter.submit([row])
    assert len(calls)==2


def test_batches_are_bounded_and_failed_batches_remain_retryable():
    rows=[{'trackId':str(10000000+i),'bundleId':f'bank.app{i}','name':f'App {i}'} for i in range(120)]
    calls=[]
    reporter=DiscoveryReporter(lambda batch:calls.append(batch) or True)
    reporter.submit(rows)
    assert [len(c) for c in calls]==[50,50,20]
    assert sum(len(c) for c in calls)==120
