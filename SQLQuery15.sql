ALTER TABLE [dbo].[users]
ADD CONSTRAINT [FK_users_rank]
FOREIGN KEY ([rank]) REFERENCES [dbo].[rank]([id]);

ALTER TABLE [dbo].[glohistory]
ADD CONSTRAINT [FK_glohistory_userid]
FOREIGN KEY ([userid]) REFERENCES [dbo].[users]([id]);

ALTER TABLE [dbo].[glohistory]
ADD CONSTRAINT [FK_glohistory_createdby]
FOREIGN KEY ([createdby]) REFERENCES [dbo].[users]([id]);

ALTER TABLE [dbo].[glohistory]
ADD CONSTRAINT [FK_glohistory_updateby]
FOREIGN KEY ([updateby]) REFERENCES [dbo].[users]([id]);

