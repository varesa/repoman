all:
	$(eval TMPDIR := $(shell mktemp -d /tmp/repoman-test.XXXXX))
	@echo Created $(TMPDIR)
	@cp repoman.conf $(TMPDIR)
	@cp test.repo $(TMPDIR)
	@sed -i 's#USER#$(USER)#g;s#TMPDIR#$(TMPDIR)#g' $(TMPDIR)/repoman.conf
	@sed -i 's#USER#$(USER)#g;s#TMPDIR#$(TMPDIR)#g' $(TMPDIR)/test.repo
	repoman -c $(TMPDIR)/repoman.conf repo-sync -v

clean:
	rm -r /tmp/repoman-test.*
